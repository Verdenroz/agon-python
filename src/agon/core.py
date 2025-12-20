"""AGON Protocol.

AGON (Adaptive Guarded Object Notation) is a schema-driven, token-efficient
encoding for lists of JSON objects.

Wire format:
    A payload is either raw JSON (a list of objects), or an AGON packet:

        {"_f":"a","c":<context_id>,"v":<hash>,"d":[row, ...]}

    Where each row is a positional array aligned with the trained schema keys.

Missing vs explicit null:
    JSON distinguishes a missing key from a present key with a null value.
    AGON preserves this distinction:

    - Explicit null is encoded as JSON null.
    - Missing fields use a reserved sentinel object {"_m": 1}.
    - Trailing missing fields may be truncated from the row.

The sentinel is reserved and must not appear in user data.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
from typing import Any

import orjson
import tiktoken

# Type aliases for clarity
SchemaNode = dict[str, Any]
Config = dict[str, Any]
TrainingConfig = dict[str, float | int | bool]


class AGONError(ValueError):
    """Raised when validation, anchoring, or strict decoding fails."""


class AGON:
    """Schema-trained encoder/decoder for AGON packets.

    Core ideas:
        - Key elimination: objects become positional rows.
        - Dictionary encoding: repeated strings can become negative integer
          pointers into a per-field dictionary.
        - Anchoring: schema is hashed to detect drift between encode/decode.

    Schema node structure:
        A schema node is a dict with:
            - k: ordered list of keys
            - t: per-key type tag: scalar | str | dict | obj | list
            - d: per-key dictionary entries for dict-encoded strings
            - s: per-key sub-schemas for obj/list
    """

    _enc = tiktoken.get_encoding("cl100k_base")

    # ---------- Token Physics ----------

    @staticmethod
    def _tk_text(text: str) -> int:
        """Count tokens for raw text string (NO CACHE to avoid memory bloat)."""
        return len(AGON._enc.encode(text))

    @staticmethod
    @lru_cache(maxsize=8192)
    def _tk_frag(s_json: str) -> int:
        """Cached token count for JSON fragments."""
        return len(AGON._enc.encode(s_json))

    @staticmethod
    def _tk_val(obj: Any) -> int:
        """Count tokens for a python value's JSON representation."""
        s = orjson.dumps(obj).decode()
        return AGON._tk_frag(s)

    # ---------- Anchoring ----------

    @staticmethod
    def _anchor(context_id: str, root: SchemaNode) -> Config:
        """Lock the schema with a SHA-256 hash."""
        blob = orjson.dumps(root, option=orjson.OPT_SORT_KEYS)
        v = hashlib.sha256(blob).hexdigest()[:16]
        return {"cid": context_id, "v": v, "schema": root}

    # ---------- Training ----------

    @staticmethod
    def train(
        data: list[dict[str, Any]],
        context_id: str,
        *,
        min_gain: float = 3.0,
        amortize: int = 50,
        max_dict_per_field: int = 100,
        enum_like_only: bool = True,
        max_enum_len: int = 64,
    ) -> Config:
        r"""Train a schema from sample data.

        The returned config is anchored with a short hash of the schema so
        `decode(..., strict=True)` can detect mismatches.

        Args:
            data: List of sample objects (dictionaries).
            context_id: String identifier for this schema.
            min_gain: Minimum net token savings required.
            amortize: Expected uses to amortize prompt cost.
            max_dict_per_field: Max entries per dictionary.
            enum_like_only: Only encode safe strings (no \n\r\t).
            max_enum_len: Max string length for dictionary.

        Returns:
            Anchored config with schema, context ID, and version hash.
        """
        cfg: TrainingConfig = {
            "min_gain": float(min_gain),
            "amortize": max(1, int(amortize)),
            "max_dict": int(max_dict_per_field),
            "enum_only": bool(enum_like_only),
            "max_len": int(max_enum_len),
        }

        if not data:
            return AGON._anchor(context_id, {"k": [], "t": {}, "d": {}, "s": {}})

        root = AGON._build_node(data, cfg)
        return AGON._anchor(context_id, root)

    @staticmethod
    def _build_node(rows: list[Any], cfg: TrainingConfig) -> SchemaNode:
        """Build a schema node from sample rows."""
        if not rows or not isinstance(rows[0], dict):
            return {"k": [], "t": {}, "d": {}, "s": {}}

        keys = sorted({k for r in rows for k in r})
        presence: Counter[str] = Counter()

        objs: dict[str, list[dict[str, Any]]] = defaultdict(list)
        lists: dict[str, list[dict[str, Any]]] = defaultdict(list)
        strings: dict[str, list[str]] = defaultdict(list)

        list_has_dicts: set[str] = set()
        is_mixed: set[str] = set()

        for r in rows:
            for k in keys:
                if k not in r:
                    continue
                presence[k] += 1
                v = r[k]
                if v is None:
                    continue

                if isinstance(v, dict):
                    objs[k].append(v)
                elif isinstance(v, list):
                    if not v:
                        pass  # Empty list is neutral
                    elif all(isinstance(x, dict) for x in v):
                        lists[k].extend(v)
                        list_has_dicts.add(k)
                    else:
                        is_mixed.add(k)
                elif isinstance(v, str):
                    strings[k].append(v)
                else:
                    is_mixed.add(k)

        types: dict[str, str] = {}
        subs: dict[str, SchemaNode] = {}
        dicts: dict[str, list[str]] = {}

        for k in keys:
            if k in is_mixed:
                types[k] = "scalar"
                continue

            if k in objs and k not in list_has_dicts and k not in strings:
                types[k] = "obj"
                subs[k] = AGON._build_node(objs[k], cfg)
                continue

            if k in list_has_dicts and k not in objs and k not in strings:
                types[k] = "list"
                subs[k] = AGON._build_node(lists[k], cfg)
                continue

            if k in strings and k not in objs and k not in list_has_dicts:
                types[k] = "str"
                AGON._optimize_string(k, strings[k], types, dicts, cfg)
                continue

            types[k] = "scalar"

        # Dense-First Sort: Maximizes trailing truncation opportunities
        total = max(1, len(rows))
        keys.sort(key=lambda k: -(presence[k] / total))

        return {"k": keys, "t": types, "d": dicts, "s": subs}

    @staticmethod
    def _optimize_string(
        key: str,
        values: list[str],
        types: dict[str, str],
        dicts: dict[str, list[str]],
        cfg: TrainingConfig,
    ) -> None:
        """Optimize string field for dictionary encoding if beneficial."""
        counts = Counter(values)
        candidates = counts.most_common()
        entries: list[str] = []
        total_savings = 0

        def is_safe(s: str) -> bool:
            if not cfg["enum_only"]:
                return True
            max_len = cfg["max_len"]
            if not isinstance(max_len, int):
                max_len = int(max_len)
            if len(s) > max_len:
                return False
            return not any(c in s for c in "\n\r\t")

        max_dict = cfg["max_dict"]
        if not isinstance(max_dict, int):
            max_dict = int(max_dict)

        for s, freq in candidates:
            if freq < 2:
                break
            if len(entries) >= max_dict:
                break
            if not is_safe(s):
                continue

            c_lit = AGON._tk_val(s)
            c_ptr = AGON._tk_val(-(len(entries) + 1))
            total_savings += (c_lit - c_ptr) * freq
            entries.append(s)

        if not entries:
            return

        prompt_cost = AGON._tk_val(key) + sum(AGON._tk_val(s) for s in entries) + len(entries) + 4

        min_gain = cfg["min_gain"]
        amortize = cfg["amortize"]
        if not isinstance(min_gain, float):
            min_gain = float(min_gain)
        if not isinstance(amortize, int):
            amortize = int(amortize)

        if (total_savings - (prompt_cost / amortize)) >= min_gain:
            types[key] = "dict"
            dicts[key] = entries

    # ---------- Encoding ----------

    @staticmethod
    def _check_coverage(data: list[dict[str, Any]], node: SchemaNode) -> bool:
        """Check if the schema covers all keys in the data.

        Returns False if data contains keys NOT in the schema.
        """
        allowed = set(node["k"])
        types: dict[str, str] = node["t"]
        subs: dict[str, SchemaNode] = node["s"]

        for r in data:
            if any(k not in allowed for k in r):
                return False

            for k, v in r.items():
                if v is None:
                    continue
                t = types.get(k, "scalar")

                if t == "obj" and isinstance(v, dict) and not AGON._check_coverage([v], subs[k]):
                    return False
                if (
                    t == "list"
                    and isinstance(v, list)
                    and v
                    and all(isinstance(x, dict) for x in v)
                    and not AGON._check_coverage(v, subs[k])
                ):
                    return False
        return True

    @staticmethod
    def encode(data: list[dict[str, Any]], config: Config, *, force_agon: bool = False) -> str:
        """Encode a list of objects.

        If `force_agon` is False, this is adaptive:
            - If the schema doesn't cover the data, return raw JSON.
            - Otherwise, return whichever (AGON vs raw JSON) tokenizes smaller.

        Args:
            data: List of objects to encode.
            config: Anchored config from train().
            force_agon: If True, always use AGON format even if larger.

        Returns:
            Either an AGON packet string or a raw JSON string.
        """
        json_str = orjson.dumps(data).decode()

        # Safety Check: Schema Drift
        if not force_agon and not AGON._check_coverage(data, config["schema"]):
            return json_str

        # Generate AGON Candidate
        agon_rows = AGON._pack(data, config["schema"])
        agon_obj = {
            "_f": "a",
            "c": config["cid"],
            "v": config["v"],
            "d": agon_rows,
        }
        agon_str = orjson.dumps(agon_obj).decode()

        if force_agon:
            return agon_str

        # Adaptive Decision: Never worse than standard JSON
        return agon_str if AGON._tk_text(agon_str) < AGON._tk_text(json_str) else json_str

    @staticmethod
    def _pack(rows: list[dict[str, Any]], node: SchemaNode) -> list[list[Any]]:
        """Pack objects into positional rows.

        Each row aligns to `node["k"]` (the ordered schema keys).

        Missing/null semantics:
            - Missing key => sentinel {"_m": 1}
            - Explicit null => JSON null
            - Trailing missing keys may be truncated from the row

        Note:
            Packed rows never contain raw dict values from user data. Nested
            objects are packed rows (lists), and missing uses the sentinel.
        """
        keys: list[str] = node["k"]
        types: dict[str, str] = node["t"]
        dicts: dict[str, list[str]] = node["d"]
        subs: dict[str, SchemaNode] = node["s"]
        val_maps = {k: {s: -(i + 1) for i, s in enumerate(lst)} for k, lst in dicts.items()}

        # Reserved marker for missing fields inside a packed row.
        # Packed rows should never contain raw dict values (see drift guards),
        # so this stays unambiguous.
        missing_sentinel: dict[str, int] = {"_m": 1}

        out: list[list[Any]] = []
        for r in rows:
            row: list[Any] = []

            for k in keys:
                # 1. Check Missing
                if k not in r:
                    row.append(missing_sentinel)
                    continue
                v = r[k]
                t = types.get(k, "scalar")

                # 2. Check Explicit Null
                if v is None:
                    row.append(None)
                    continue

                # 3. Handle Types & Schema Drift
                if t == "obj":
                    if isinstance(v, dict):
                        row.append(AGON._pack([v], subs[k])[0])
                    else:
                        row.append(v)
                elif t == "list":
                    if isinstance(v, list) and all(isinstance(x, dict) for x in v):
                        row.append(AGON._pack(v, subs[k]))
                    else:
                        row.append(v)
                elif t == "dict" and v in val_maps.get(k, {}):
                    row.append(val_maps[k][v])
                else:
                    row.append(v)

            # Truncate only trailing MISSING keys
            while row and isinstance(row[-1], dict) and row[-1] == missing_sentinel:
                row.pop()
            out.append(row)
        return out

    # ---------- Decoding ----------

    @staticmethod
    def decode(payload: str, config: Config, strict: bool = True) -> list[dict[str, Any]]:
        """Decode an AGON packet or raw JSON list.

        With `strict=True`, this validates the schema anchor (`cid`/`v`) and
        performs shape checks to guard against schema drift corruption.

        Args:
            payload: AGON packet or raw JSON string.
            config: Anchored config from train().
            strict: If True, raise errors on validation failures.

        Returns:
            List of decoded dictionaries.
        """
        try:
            packet = orjson.loads(payload)
        except orjson.JSONDecodeError as e:
            if strict:
                raise AGONError(f"Invalid JSON: {e}") from e
            return []

        # Adaptive Fallback: Raw JSON list
        if isinstance(packet, list):
            return packet

        # AGON Decode
        if isinstance(packet, dict) and packet.get("_f") == "a":
            if strict:
                if packet.get("c") != config["cid"]:
                    raise AGONError("CID Mismatch")
                if packet.get("v") != config["v"]:
                    raise AGONError("Version Mismatch")

            d_rows = packet.get("d")
            if not isinstance(d_rows, list):
                if strict:
                    raise AGONError("Payload 'd' must be a list")
                return []

            return AGON._unpack(d_rows, config["schema"], strict)

        if strict:
            raise AGONError("Unknown format")
        return []

    @staticmethod
    def _validate_packed_row_structure(row: Any, sub_node: SchemaNode) -> bool:
        """Validate that a value is a valid packed row for a sub-schema.

        Used as a drift guard during decode.
        """
        if not isinstance(row, list):
            return False

        keys: list[str] = sub_node["k"]
        types: dict[str, str] = sub_node["t"]

        if len(row) > len(keys):
            return False

        for i, val in enumerate(row):
            if val is None:
                continue

            # Allow the reserved missing sentinel inside packed rows.
            if isinstance(val, dict) and val == {"_m": 1}:
                continue

            k = keys[i]
            t = types.get(k, "scalar")

            if isinstance(val, dict):
                return False  # Packed rows never have raw dicts

            # Nested Object: Must be a list (packed row)
            if t == "obj" and not isinstance(val, list):
                return False

            # Nested List: Must be a list of lists (packed rows)
            if t == "list":
                if not isinstance(val, list):
                    return False
                if val and not all(isinstance(x, list) for x in val):
                    return False

        return True

    @staticmethod
    def _unpack(rows: list[Any], node: SchemaNode, strict: bool) -> list[dict[str, Any]]:
        """Unpack positional rows back into dictionaries."""
        keys: list[str] = node["k"]
        types: dict[str, str] = node["t"]
        dicts: dict[str, list[str]] = node["d"]
        subs: dict[str, SchemaNode] = node["s"]
        inv_maps = {k: {-(i + 1): s for i, s in enumerate(lst)} for k, lst in dicts.items()}

        out: list[dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, list):
                if strict:
                    raise AGONError("Row must be a list")
                continue

            obj: dict[str, Any] = {}
            limit = min(len(r), len(keys))
            for i in range(limit):
                k = keys[i]
                v = r[i]
                t = types.get(k, "scalar")

                # Reserved missing sentinel => key must remain absent.
                if isinstance(v, dict) and v == {"_m": 1}:
                    continue

                if v is None:
                    obj[k] = None
                    continue

                if t == "obj":
                    # Drift Guard: Strict shape check against sub-schema
                    if AGON._validate_packed_row_structure(v, subs[k]):
                        obj[k] = AGON._unpack([v], subs[k], strict)[0]
                    else:
                        obj[k] = v
                elif t == "list":
                    # Drift Guard: Must be list-of-lists (or empty)
                    if isinstance(v, list) and (not v or all(isinstance(x, list) for x in v)):
                        obj[k] = AGON._unpack(v, subs[k], strict)
                    else:
                        obj[k] = v
                elif t == "dict" and isinstance(v, int) and v < 0:
                    mapped = inv_maps[k].get(v)
                    if mapped is None:
                        if strict:
                            raise AGONError(f"Invalid dict ref {v} for {k}")
                        obj[k] = v
                    else:
                        obj[k] = mapped
                else:
                    obj[k] = v
            out.append(obj)
        return out

    # ---------- Prompt & Schema ----------

    @staticmethod
    def system_prompt(config: Config) -> str:
        """Generate a compact, model-facing description of the protocol.

        Args:
            config: Anchored config from train().

        Returns:
            System prompt string describing AGON format.
        """
        schema_view = {
            "keys": config["schema"]["k"],
            "dicts": config["schema"]["d"],
            "subs": {k: sub["k"] for k, sub in config["schema"]["s"].items()},
        }
        schema_str = orjson.dumps(schema_view).decode()

        return (
            f"AGON(c='{config['cid']}',v='{config['v']}'). "
            f'Output JSON: {{"_f":"a","c":"{config["cid"]}","v":"{config["v"]}","d":[[...]]}}. '
            "Rows are positional. Truncate trailing missing fields. "
            "Non-trailing missing fields use the sentinel {\"_m\":1}. "
            "Explicit nulls must be kept as null. "
            "Dicts use negative ints.\n"
            f"Schema: {schema_str}"
        )

    @staticmethod
    def get_json_schema(config: Config) -> dict[str, Any]:
        """Generate strict JSON Schema for constrained decoding.

        Compatible with OpenAI Structured Outputs and XGrammar.

        Args:
            config: Anchored config from train().

        Returns:
            JSON Schema dictionary.
        """
        return {
            "type": "object",
            "properties": {
                "_f": {"const": "a"},
                "c": {"const": config["cid"]},
                "v": {"const": config["v"]},
                "d": AGON._to_json_schema_node(config["schema"]),
            },
            "required": ["_f", "c", "v", "d"],
            "additionalProperties": False,
        }

    @staticmethod
    def _to_json_schema_node(node: SchemaNode) -> dict[str, Any]:
        """Convert a schema node to a JSON Schema fragment.

        The schema permits the reserved missing sentinel object {"_m": 1} in
        any position so structured outputs can represent missing non-trailing
        fields.
        """
        keys: list[str] = node["k"]
        types: dict[str, str] = node["t"]
        subs: dict[str, SchemaNode] = node["s"]
        dicts: dict[str, list[str]] = node["d"]

        missing_sentinel_schema: dict[str, Any] = {
            "type": "object",
            "properties": {"_m": {"const": 1}},
            "required": ["_m"],
            "additionalProperties": False,
        }

        prefix_items: list[dict[str, Any]] = []
        for k in keys:
            t = types.get(k, "scalar")
            base_schema: list[dict[str, Any]] = [missing_sentinel_schema, {"type": "null"}]

            if t == "obj":
                base_schema.append(AGON._to_json_schema_node(subs[k])["items"])
            elif t == "list":
                base_schema.append(AGON._to_json_schema_node(subs[k]))
            elif t == "dict":
                dict_len = len(dicts.get(k, []))
                if dict_len > 0:
                    base_schema.append({"type": "integer", "maximum": -1, "minimum": -dict_len})
                base_schema.append({"type": "string"})
            else:
                base_schema.append({"type": ["string", "number", "boolean", "object", "array"]})

            prefix_items.append({"anyOf": base_schema})

        return {
            "type": "array",
            "items": {
                "type": "array",
                "prefixItems": prefix_items,
                "maxItems": len(keys),
            },
        }


class AgonClient:
    """High-level client for managing AGON schemas across multiple endpoints."""

    def __init__(self) -> None:
        """Initialize the client with an empty config registry."""
        self.configs: dict[str, Config] = {}

    def register(self, endpoint: str, sample: list[dict[str, Any]]) -> None:
        """Register an endpoint with sample data for schema training."""
        self.configs[endpoint] = AGON.train(sample, endpoint)

    def encode(self, endpoint: str, data: list[dict[str, Any]]) -> str:
        """Encode data for a registered endpoint."""
        if endpoint not in self.configs:
            return orjson.dumps(data).decode()
        return AGON.encode(data, self.configs[endpoint])

    def decode(self, endpoint: str, payload: str, strict: bool = True) -> list[dict[str, Any]]:
        """Decode payload for a registered endpoint."""
        if endpoint not in self.configs:
            try:
                p = orjson.loads(payload)
                if isinstance(p, list):
                    return p
                if isinstance(p, dict) and p.get("_f") == "j":
                    return p["d"]
            except orjson.JSONDecodeError:
                pass
            return []
        return AGON.decode(payload, self.configs[endpoint], strict=strict)

    def get_prompt(self, endpoint: str) -> str:
        """Get system prompt for a registered endpoint."""
        return AGON.system_prompt(self.configs[endpoint])

    def get_tool_schema(self, endpoint: str) -> dict[str, Any]:
        """Get tool schema for a registered endpoint."""
        return {
            "type": "json_schema",
            "json_schema": {
                "name": f"agon_{endpoint}",
                "schema": AGON.get_json_schema(self.configs[endpoint]),
                "strict": True,
            },
        }
