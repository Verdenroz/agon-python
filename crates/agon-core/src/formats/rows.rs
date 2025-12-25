//! AGONRows format encoder/decoder
//!
//! Row-based encoding with tabular format for arrays of uniform objects.
//!
//! Format structure:
//!     @AGON rows
//!     @D=<delimiter>  # optional, default: \t
//!     <data>

use regex::Regex;
use serde_json::{Map, Value};
use std::sync::LazyLock;

use crate::error::{AgonError, Result};

const HEADER: &str = "@AGON rows";
const DEFAULT_DELIMITER: &str = "\t";
const INDENT: &str = "  ";

// Regex patterns for parsing
static TABULAR_HEADER_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^(\w*)\[(\d+)\]\{(.+)\}$").unwrap());
static PRIMITIVE_ARRAY_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^(\w*)\[(\d+)\]:\s*(.*)$").unwrap());
static LIST_ARRAY_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^(\w*)\[(\d+)\]:$").unwrap());
static KEY_VALUE_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^([^:]+):\s*(.*)$").unwrap());
static NUMBER_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$").unwrap());

/// Encode data to AGONRows format
pub fn encode(data: &Value, include_header: bool) -> Result<String> {
    let mut lines = Vec::new();
    let delimiter = DEFAULT_DELIMITER;

    if include_header {
        lines.push(HEADER.to_string());
        lines.push(String::new());
    }

    encode_value(data, &mut lines, 0, delimiter, None);

    Ok(lines.join("\n"))
}

/// Decode AGONRows payload
pub fn decode(payload: &str) -> Result<Value> {
    let lines: Vec<&str> = payload.lines().collect();
    if lines.is_empty() {
        return Err(AgonError::DecodingError("Empty payload".to_string()));
    }

    let mut idx = 0;

    // Parse header
    let header_line = lines[idx].trim();
    if !header_line.starts_with("@AGON rows") {
        return Err(AgonError::DecodingError(format!(
            "Invalid header: {}",
            header_line
        )));
    }
    idx += 1;

    // Parse optional delimiter
    let delimiter = if idx < lines.len() && lines[idx].starts_with("@D=") {
        let d = parse_delimiter(&lines[idx][3..]);
        idx += 1;
        d
    } else {
        DEFAULT_DELIMITER.to_string()
    };

    // Skip blank lines
    while idx < lines.len() && lines[idx].trim().is_empty() {
        idx += 1;
    }

    if idx >= lines.len() {
        return Ok(Value::Null);
    }

    let (result, _) = decode_value(&lines, idx, 0, &delimiter)?;
    Ok(result)
}

// ============================================================================
// Encoding helpers
// ============================================================================

fn needs_quote(s: &str, delimiter: &str) -> bool {
    if s.is_empty() {
        return true;
    }
    if s.trim() != s {
        return true;
    }
    if s.contains(delimiter) {
        return true;
    }
    if s.contains('\n') || s.contains('\r') || s.contains('\\') || s.contains('"') {
        return true;
    }
    let first = s.chars().next().unwrap();
    if first == '@' || first == '#' || first == '-' {
        return true;
    }
    let lower = s.to_lowercase();
    if lower == "true" || lower == "false" || lower == "null" {
        return true;
    }
    NUMBER_RE.is_match(s)
}

fn quote_string(s: &str) -> String {
    let escaped = s
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
        .replace('\t', "\\t");
    format!("\"{}\"", escaped)
}

fn unquote_string(s: &str) -> String {
    if !(s.starts_with('"') && s.ends_with('"')) {
        return s.to_string();
    }
    let inner = &s[1..s.len() - 1];
    let mut result = String::new();
    let mut chars = inner.chars().peekable();

    while let Some(c) = chars.next() {
        if c == '\\' {
            match chars.next() {
                Some('n') => result.push('\n'),
                Some('r') => result.push('\r'),
                Some('t') => result.push('\t'),
                Some('\\') => result.push('\\'),
                Some('"') => result.push('"'),
                Some(other) => result.push(other),
                None => result.push('\\'),
            }
        } else {
            result.push(c);
        }
    }
    result
}

fn encode_primitive(val: &Value, delimiter: &str) -> String {
    match val {
        Value::Null => "null".to_string(),
        Value::Bool(b) => if *b { "true" } else { "false" }.to_string(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => {
            if needs_quote(s, delimiter) {
                quote_string(s)
            } else {
                s.clone()
            }
        }
        _ => serde_json::to_string(val).unwrap_or_default(),
    }
}

fn parse_primitive(s: &str) -> Value {
    let s = s.trim();
    if s.is_empty() {
        return Value::Null;
    }

    // Quoted string
    if s.starts_with('"') && s.ends_with('"') {
        return Value::String(unquote_string(s));
    }

    // Boolean/null
    let lower = s.to_lowercase();
    if lower == "null" {
        return Value::Null;
    }
    if lower == "true" {
        return Value::Bool(true);
    }
    if lower == "false" {
        return Value::Bool(false);
    }

    // Number
    if NUMBER_RE.is_match(s) {
        if s.contains('.') || s.to_lowercase().contains('e') {
            if let Ok(f) = s.parse::<f64>()
                && let Some(n) = serde_json::Number::from_f64(f)
            {
                return Value::Number(n);
            }
        } else if let Ok(i) = s.parse::<i64>() {
            return Value::Number(i.into());
        }
    }

    Value::String(s.to_string())
}

fn parse_delimiter(d: &str) -> String {
    let d = d.trim();
    match d {
        "\\t" => "\t".to_string(),
        "\\n" => "\n".to_string(),
        _ => d.to_string(),
    }
}

fn is_uniform_array(arr: &[Value]) -> (bool, Vec<String>) {
    if arr.is_empty() {
        return (false, vec![]);
    }

    // Check all are objects
    if !arr.iter().all(|v| v.is_object()) {
        return (false, vec![]);
    }

    // Check all values are primitives
    for obj in arr {
        if let Some(map) = obj.as_object() {
            for v in map.values() {
                if v.is_object() || v.is_array() {
                    return (false, vec![]);
                }
            }
        }
    }

    // Collect keys in order
    let mut key_order = Vec::new();
    for obj in arr {
        if let Some(map) = obj.as_object() {
            for k in map.keys() {
                if !key_order.contains(k) {
                    key_order.push(k.clone());
                }
            }
        }
    }

    (true, key_order)
}

fn is_primitive_array(arr: &[Value]) -> bool {
    arr.iter().all(|v| !v.is_object() && !v.is_array())
}

fn encode_value(
    val: &Value,
    lines: &mut Vec<String>,
    depth: usize,
    delimiter: &str,
    name: Option<&str>,
) {
    let indent = INDENT.repeat(depth);

    match val {
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {
            let encoded = encode_primitive(val, delimiter);
            if let Some(n) = name {
                lines.push(format!("{}{}: {}", indent, n, encoded));
            } else {
                lines.push(format!("{}{}", indent, encoded));
            }
        }
        Value::Array(arr) => {
            encode_array(arr, lines, depth, delimiter, name);
        }
        Value::Object(obj) => {
            encode_object(obj, lines, depth, delimiter, name);
        }
    }
}

fn encode_array(
    arr: &[Value],
    lines: &mut Vec<String>,
    depth: usize,
    delimiter: &str,
    name: Option<&str>,
) {
    let indent = INDENT.repeat(depth);

    if arr.is_empty() {
        if let Some(n) = name {
            lines.push(format!("{}{}[0]:", indent, n));
        } else {
            lines.push(format!("{}[0]:", indent));
        }
        return;
    }

    // Check for uniform objects (tabular format)
    let (is_uniform, fields) = is_uniform_array(arr);
    if is_uniform && !fields.is_empty() {
        let header = fields.join(delimiter);
        if let Some(n) = name {
            lines.push(format!("{}{}[{}]{{{}}}", indent, n, arr.len(), header));
        } else {
            lines.push(format!("{}[{}]{{{}}}", indent, arr.len(), header));
        }

        for obj in arr {
            if let Some(map) = obj.as_object() {
                let row: Vec<String> = fields
                    .iter()
                    .map(|f| {
                        map.get(f)
                            .map(|v| encode_primitive(v, delimiter))
                            .unwrap_or_default()
                    })
                    .collect();
                lines.push(format!("{}{}", indent, row.join(delimiter)));
            }
        }
        return;
    }

    // Primitive array (inline format)
    if is_primitive_array(arr) {
        let values: Vec<String> = arr.iter().map(|v| encode_primitive(v, delimiter)).collect();
        if let Some(n) = name {
            lines.push(format!(
                "{}{}[{}]: {}",
                indent,
                n,
                arr.len(),
                values.join(delimiter)
            ));
        } else {
            lines.push(format!(
                "{}[{}]: {}",
                indent,
                arr.len(),
                values.join(delimiter)
            ));
        }
        return;
    }

    // Mixed/nested array
    if let Some(n) = name {
        lines.push(format!("{}{}[{}]:", indent, n, arr.len()));
    } else {
        lines.push(format!("{}[{}]:", indent, arr.len()));
    }

    for item in arr {
        if item.is_object() {
            encode_list_item_object(item.as_object().unwrap(), lines, depth + 1, delimiter);
        } else {
            lines.push(format!(
                "{}  - {}",
                indent,
                encode_primitive(item, delimiter)
            ));
        }
    }
}

fn encode_list_item_object(
    obj: &Map<String, Value>,
    lines: &mut Vec<String>,
    depth: usize,
    delimiter: &str,
) {
    let indent = INDENT.repeat(depth);
    let mut first = true;

    for (k, v) in obj {
        let prefix = if first {
            format!("{}- ", indent)
        } else {
            format!("{}  ", indent)
        };
        first = false;

        match v {
            Value::Object(nested) => {
                lines.push(format!("{}{}:", prefix, k));
                for (nk, nv) in nested {
                    if nv.is_object() || nv.is_array() {
                        encode_value(nv, lines, depth + 2, delimiter, Some(nk));
                    } else {
                        lines.push(format!(
                            "{}    {}: {}",
                            indent,
                            nk,
                            encode_primitive(nv, delimiter)
                        ));
                    }
                }
            }
            Value::Array(_) => {
                lines.push(format!("{}{}:", prefix, k));
                encode_value(v, lines, depth + 2, delimiter, None);
            }
            _ => {
                lines.push(format!(
                    "{}{}: {}",
                    prefix,
                    k,
                    encode_primitive(v, delimiter)
                ));
            }
        }
    }
}

fn encode_object(
    obj: &Map<String, Value>,
    lines: &mut Vec<String>,
    depth: usize,
    delimiter: &str,
    name: Option<&str>,
) {
    let indent = INDENT.repeat(depth);
    let mut actual_depth = depth;

    if let Some(n) = name {
        lines.push(format!("{}{}:", indent, n));
        actual_depth += 1;
    }

    let actual_indent = INDENT.repeat(actual_depth);

    for (k, v) in obj {
        match v {
            Value::Object(_) | Value::Array(_) => {
                encode_value(v, lines, actual_depth, delimiter, Some(k));
            }
            _ => {
                lines.push(format!(
                    "{}{}: {}",
                    actual_indent,
                    k,
                    encode_primitive(v, delimiter)
                ));
            }
        }
    }
}

// ============================================================================
// Decoding helpers
// ============================================================================

fn get_indent_depth(line: &str) -> usize {
    let stripped = line.trim_start_matches(' ');
    let spaces = line.len() - stripped.len();
    spaces / 2
}

fn split_row(values_str: &str, delimiter: &str) -> Vec<String> {
    if delimiter.len() == 1 {
        // Fast path for single-char delimiter (common case: tab)
        let delim_char = delimiter.chars().next().unwrap();
        let mut result = Vec::new();
        let mut current = String::new();
        let mut in_quote = false;
        let mut escape_next = false;

        for c in values_str.chars() {
            if escape_next {
                current.push(c);
                escape_next = false;
                continue;
            }

            if c == '\\' && in_quote {
                escape_next = true;
                current.push(c);
                continue;
            }

            if c == '"' {
                in_quote = !in_quote;
                current.push(c);
            } else if c == delim_char && !in_quote {
                result.push(current);
                current = String::new();
            } else {
                current.push(c);
            }
        }

        result.push(current);
        result
    } else {
        // Multi-char delimiter (less common)
        let mut result = Vec::new();
        let mut current = String::new();
        let mut in_quote = false;
        let mut i = 0;
        let chars: Vec<char> = values_str.chars().collect();

        while i < chars.len() {
            let c = chars[i];

            if c == '"' {
                in_quote = !in_quote;
                current.push(c);
                i += 1;
            } else if !in_quote && values_str[i..].starts_with(delimiter) {
                result.push(current);
                current = String::new();
                i += delimiter.len();
            } else {
                current.push(c);
                i += 1;
            }
        }

        result.push(current);
        result
    }
}

fn decode_value(
    lines: &[&str],
    idx: usize,
    depth: usize,
    delimiter: &str,
) -> Result<(Value, usize)> {
    if idx >= lines.len() {
        return Ok((Value::Null, idx));
    }

    let line = lines[idx];
    if get_indent_depth(line) < depth {
        return Ok((Value::Null, idx));
    }

    let stripped = line.trim();

    if stripped.is_empty() || stripped.starts_with('#') {
        return decode_value(lines, idx + 1, depth, delimiter);
    }

    // Check for tabular array
    if let Some(caps) = TABULAR_HEADER_RE.captures(stripped) {
        let name = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        if !name.is_empty() {
            return decode_object(lines, idx, depth, delimiter);
        }
        return decode_tabular_array(lines, idx, depth, delimiter, &caps);
    }

    // Check for primitive array
    if let Some(caps) = PRIMITIVE_ARRAY_RE.captures(stripped) {
        let name = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        let values_part = caps.get(3).map(|m| m.as_str()).unwrap_or("").trim();
        if !values_part.is_empty() {
            if !name.is_empty() {
                return decode_object(lines, idx, depth, delimiter);
            }
            return decode_primitive_array(&caps, delimiter, idx);
        }
    }

    // Check for list array
    if let Some(caps) = LIST_ARRAY_RE.captures(stripped) {
        let name = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        if !name.is_empty() {
            return decode_object(lines, idx, depth, delimiter);
        }
        return decode_list_array(lines, idx, depth, delimiter, &caps);
    }

    // Check for key:value
    if KEY_VALUE_RE.is_match(stripped) {
        return decode_object(lines, idx, depth, delimiter);
    }

    Err(AgonError::ParseError {
        line: idx,
        message: format!("Cannot parse: {}", stripped),
    })
}

fn decode_tabular_array(
    lines: &[&str],
    idx: usize,
    _depth: usize,
    delimiter: &str,
    caps: &regex::Captures,
) -> Result<(Value, usize)> {
    let name = caps.get(1).map(|m| m.as_str()).unwrap_or("");
    let count: usize = caps
        .get(2)
        .map(|m| m.as_str())
        .unwrap_or("0")
        .parse()
        .unwrap_or(0);
    let fields_str = caps.get(3).map(|m| m.as_str()).unwrap_or("");
    let fields: Vec<&str> = fields_str.split(delimiter).map(|s| s.trim()).collect();

    let mut idx = idx + 1;
    let mut result = Vec::new();

    while idx < lines.len() && result.len() < count {
        let row_line = lines[idx].trim();
        if row_line.is_empty() || row_line.starts_with('#') {
            idx += 1;
            continue;
        }

        let values = split_row(row_line, delimiter);
        let mut obj = Map::new();

        for (i, field) in fields.iter().enumerate() {
            if i < values.len() {
                let raw = &values[i];
                let val = parse_primitive(raw);
                if !matches!(val, Value::Null) || !raw.trim().is_empty() {
                    obj.insert(field.to_string(), val);
                }
            }
        }

        result.push(Value::Object(obj));
        idx += 1;
    }

    let arr = Value::Array(result);
    if !name.is_empty() {
        let mut wrapper = Map::new();
        wrapper.insert(name.to_string(), arr);
        Ok((Value::Object(wrapper), idx))
    } else {
        Ok((arr, idx))
    }
}

fn decode_primitive_array(
    caps: &regex::Captures,
    delimiter: &str,
    idx: usize,
) -> Result<(Value, usize)> {
    let name = caps.get(1).map(|m| m.as_str()).unwrap_or("");
    let values_str = caps.get(3).map(|m| m.as_str()).unwrap_or("");

    let arr = if values_str.trim().is_empty() {
        Value::Array(vec![])
    } else {
        let values = split_row(values_str, delimiter);
        Value::Array(values.iter().map(|v| parse_primitive(v)).collect())
    };

    if !name.is_empty() {
        let mut wrapper = Map::new();
        wrapper.insert(name.to_string(), arr);
        Ok((Value::Object(wrapper), idx + 1))
    } else {
        Ok((arr, idx + 1))
    }
}

fn decode_list_array(
    lines: &[&str],
    idx: usize,
    depth: usize,
    delimiter: &str,
    caps: &regex::Captures,
) -> Result<(Value, usize)> {
    let name = caps.get(1).map(|m| m.as_str()).unwrap_or("");
    let count: usize = caps
        .get(2)
        .map(|m| m.as_str())
        .unwrap_or("0")
        .parse()
        .unwrap_or(0);

    let mut idx = idx + 1;
    let mut result = Vec::new();
    let base_depth = depth + 1;

    while idx < lines.len() && result.len() < count {
        let line = lines[idx];
        if line.trim().is_empty() || line.trim().starts_with('#') {
            idx += 1;
            continue;
        }

        let line_depth = get_indent_depth(line);
        if line_depth < base_depth {
            break;
        }

        let stripped = line.trim();
        if let Some(item_str) = stripped.strip_prefix("- ") {
            let item_str = item_str.trim();
            if KEY_VALUE_RE.is_match(item_str) {
                let (obj, new_idx) = decode_list_item_object(lines, idx, base_depth, delimiter)?;
                result.push(obj);
                idx = new_idx;
            } else {
                result.push(parse_primitive(item_str));
                idx += 1;
            }
        } else {
            break;
        }
    }

    let arr = Value::Array(result);
    if !name.is_empty() {
        let mut wrapper = Map::new();
        wrapper.insert(name.to_string(), arr);
        Ok((Value::Object(wrapper), idx))
    } else {
        Ok((arr, idx))
    }
}

fn decode_list_item_object(
    lines: &[&str],
    idx: usize,
    base_depth: usize,
    delimiter: &str,
) -> Result<(Value, usize)> {
    let mut obj = Map::new();
    let item_depth = base_depth;

    // Parse first line (starts with -)
    let first_line = lines[idx].trim();
    let first_content = first_line.strip_prefix("- ").unwrap_or(first_line).trim();

    let mut idx = idx;

    if let Some(caps) = KEY_VALUE_RE.captures(first_content) {
        let key = caps.get(1).map(|m| m.as_str()).unwrap_or("").trim();
        let val_str = caps.get(2).map(|m| m.as_str()).unwrap_or("").trim();

        if !val_str.is_empty() {
            obj.insert(key.to_string(), parse_primitive(val_str));
            idx += 1;
        } else {
            idx += 1;
            if idx < lines.len() {
                let next_depth = get_indent_depth(lines[idx]);
                if next_depth > item_depth + 1 {
                    let (nested, new_idx) = decode_value(lines, idx, next_depth, delimiter)?;
                    obj.insert(key.to_string(), nested);
                    idx = new_idx;
                } else {
                    // Empty object - no nested content at higher depth
                    obj.insert(key.to_string(), Value::Object(Map::new()));
                }
            } else {
                obj.insert(key.to_string(), Value::Object(Map::new()));
            }
        }
    } else {
        idx += 1;
    }

    // Parse continuation lines
    while idx < lines.len() {
        let line = lines[idx];
        if line.trim().is_empty() {
            idx += 1;
            continue;
        }

        let line_depth = get_indent_depth(line);
        if line_depth <= item_depth {
            break;
        }

        let stripped = line.trim();

        if let Some(caps) = KEY_VALUE_RE.captures(stripped) {
            let key = caps.get(1).map(|m| m.as_str()).unwrap_or("").trim();
            let val_str = caps.get(2).map(|m| m.as_str()).unwrap_or("").trim();

            if !val_str.is_empty() {
                obj.insert(key.to_string(), parse_primitive(val_str));
                idx += 1;
            } else {
                idx += 1;
                if idx < lines.len() {
                    let next_depth = get_indent_depth(lines[idx]);
                    if next_depth > line_depth {
                        let (nested, new_idx) = decode_value(lines, idx, next_depth, delimiter)?;
                        obj.insert(key.to_string(), nested);
                        idx = new_idx;
                    } else {
                        // Empty object - no nested content
                        obj.insert(key.to_string(), Value::Object(Map::new()));
                    }
                } else {
                    obj.insert(key.to_string(), Value::Object(Map::new()));
                }
            }
        } else {
            idx += 1;
        }
    }

    Ok((Value::Object(obj), idx))
}

fn decode_object(
    lines: &[&str],
    idx: usize,
    _depth: usize,
    delimiter: &str,
) -> Result<(Value, usize)> {
    let mut result = Map::new();
    if idx >= lines.len() {
        return Ok((Value::Object(result), idx));
    }

    let base_depth = get_indent_depth(lines[idx]);
    let mut idx = idx;

    while idx < lines.len() {
        let line = lines[idx];
        if line.trim().is_empty() || line.trim().starts_with('#') {
            idx += 1;
            continue;
        }

        let line_depth = get_indent_depth(line);
        if line_depth < base_depth {
            break;
        }

        let stripped = line.trim();

        // Check for array patterns first
        if let Some(caps) = TABULAR_HEADER_RE.captures(stripped) {
            let (nested, new_idx) = decode_tabular_array(lines, idx, line_depth, delimiter, &caps)?;
            if let Value::Object(map) = nested {
                for (k, v) in map {
                    result.insert(k, v);
                }
            }
            idx = new_idx;
            continue;
        }

        if let Some(caps) = PRIMITIVE_ARRAY_RE.captures(stripped) {
            let values_part = caps.get(3).map(|m| m.as_str()).unwrap_or("").trim();
            if !values_part.is_empty() {
                let (nested, new_idx) = decode_primitive_array(&caps, delimiter, idx)?;
                if let Value::Object(map) = nested {
                    for (k, v) in map {
                        result.insert(k, v);
                    }
                }
                idx = new_idx;
                continue;
            }
        }

        if let Some(caps) = LIST_ARRAY_RE.captures(stripped) {
            let (nested, new_idx) = decode_list_array(lines, idx, line_depth, delimiter, &caps)?;
            if let Value::Object(map) = nested {
                for (k, v) in map {
                    result.insert(k, v);
                }
            }
            idx = new_idx;
            continue;
        }

        if let Some(caps) = KEY_VALUE_RE.captures(stripped) {
            let key = caps.get(1).map(|m| m.as_str()).unwrap_or("").trim();
            let val_str = caps.get(2).map(|m| m.as_str()).unwrap_or("").trim();

            if !val_str.is_empty() {
                result.insert(key.to_string(), parse_primitive(val_str));
                idx += 1;
            } else {
                idx += 1;
                if idx < lines.len() {
                    let next_depth = get_indent_depth(lines[idx]);
                    if next_depth > line_depth {
                        let (nested, new_idx) = decode_value(lines, idx, next_depth, delimiter)?;
                        result.insert(key.to_string(), nested);
                        idx = new_idx;
                    } else {
                        result.insert(key.to_string(), Value::Object(Map::new()));
                    }
                } else {
                    result.insert(key.to_string(), Value::Object(Map::new()));
                }
            }
        } else {
            break;
        }
    }

    Ok((Value::Object(result), idx))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // ========================================================================
    // Encoding tests
    // ========================================================================

    #[test]
    fn test_encode_simple_array() {
        let data = json!([
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ]);
        let encoded = encode(&data, false).unwrap();
        assert!(encoded.contains("[2]{"));
        assert!(encoded.contains("Alice"));
    }

    #[test]
    fn test_encode_with_header() {
        let data = json!({"name": "test"});
        let encoded = encode(&data, true).unwrap();
        assert!(encoded.starts_with("@AGON rows"));
    }

    #[test]
    fn test_encode_without_header() {
        let data = json!({"name": "test"});
        let encoded = encode(&data, false).unwrap();
        assert!(!encoded.contains("@AGON"));
    }

    #[test]
    fn test_encode_primitives() {
        let data = json!({
            "string": "hello",
            "number": 42,
            "float": 3.15,
            "bool_true": true,
            "bool_false": false,
            "null_val": null
        });
        let encoded = encode(&data, false).unwrap();
        assert!(encoded.contains("string: hello"));
        assert!(encoded.contains("number: 42"));
        assert!(encoded.contains("float: 3.15"));
        assert!(encoded.contains("bool_true: true"));
        assert!(encoded.contains("bool_false: false"));
        assert!(encoded.contains("null_val: null"));
    }

    #[test]
    fn test_encode_empty_array() {
        let data = json!({"items": []});
        let encoded = encode(&data, false).unwrap();
        assert!(encoded.contains("items[0]:"));
    }

    #[test]
    fn test_encode_primitive_array() {
        let data = json!({"nums": [1, 2, 3]});
        let encoded = encode(&data, false).unwrap();
        assert!(encoded.contains("nums[3]:"));
    }

    #[test]
    fn test_encode_nested_object() {
        let data = json!({
            "outer": {
                "inner": {
                    "value": 42
                }
            }
        });
        let encoded = encode(&data, false).unwrap();
        assert!(encoded.contains("outer:"));
        assert!(encoded.contains("inner:"));
        assert!(encoded.contains("value: 42"));
    }

    // ========================================================================
    // Decoding tests
    // ========================================================================

    #[test]
    fn test_decode_empty_payload() {
        let result = decode("");
        assert!(result.is_err());
    }

    #[test]
    fn test_decode_invalid_header() {
        let result = decode("invalid header");
        assert!(result.is_err());
    }

    #[test]
    fn test_decode_header_only() {
        let result = decode("@AGON rows\n\n").unwrap();
        assert!(result.is_null());
    }

    #[test]
    fn test_decode_simple_object() {
        let payload = "@AGON rows\n\nname: Alice\nage: 30";
        let decoded = decode(payload).unwrap();
        assert_eq!(decoded["name"], "Alice");
        assert_eq!(decoded["age"], 30);
    }

    #[test]
    fn test_decode_tabular_array() {
        let payload = "@AGON rows\n\n[2]{id\tname}\n1\tAlice\n2\tBob";
        let decoded = decode(payload).unwrap();
        assert!(decoded.is_array());
        let arr = decoded.as_array().unwrap();
        assert_eq!(arr.len(), 2);
        assert_eq!(arr[0]["id"], 1);
        assert_eq!(arr[0]["name"], "Alice");
    }

    #[test]
    fn test_decode_named_tabular_array() {
        let payload = "@AGON rows\n\nusers[2]{id\tname}\n1\tAlice\n2\tBob";
        let decoded = decode(payload).unwrap();
        assert!(decoded.is_object());
        let users = decoded["users"].as_array().unwrap();
        assert_eq!(users.len(), 2);
    }

    #[test]
    fn test_decode_primitive_array() {
        let payload = "@AGON rows\n\nnums[3]: 1\t2\t3";
        let decoded = decode(payload).unwrap();
        let nums = decoded["nums"].as_array().unwrap();
        assert_eq!(nums.len(), 3);
        assert_eq!(nums[0], 1);
        assert_eq!(nums[1], 2);
        assert_eq!(nums[2], 3);
    }

    #[test]
    fn test_decode_custom_delimiter() {
        let payload = "@AGON rows\n@D=\\t\n\nname: test";
        let decoded = decode(payload).unwrap();
        assert_eq!(decoded["name"], "test");
    }

    // ========================================================================
    // Roundtrip tests
    // ========================================================================

    #[test]
    fn test_roundtrip() {
        let data = json!({
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"}
            ]
        });
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();

        assert!(decoded.is_object());
        let users = decoded.get("users").unwrap();
        assert!(users.is_array());
        assert_eq!(users.as_array().unwrap().len(), 2);
    }

    #[test]
    fn test_roundtrip_nested_object() {
        let data = json!({
            "company": {
                "name": "ACME",
                "address": {
                    "city": "Seattle"
                }
            }
        });
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert_eq!(decoded["company"]["name"], "ACME");
        assert_eq!(decoded["company"]["address"]["city"], "Seattle");
    }

    #[test]
    fn test_roundtrip_empty_object() {
        let data = json!({});
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert!(
            decoded.is_null() || (decoded.is_object() && decoded.as_object().unwrap().is_empty())
        );
    }

    #[test]
    fn test_roundtrip_mixed_array() {
        let data = json!({
            "items": [1, "two", true, null]
        });
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        let items = decoded["items"].as_array().unwrap();
        assert_eq!(items.len(), 4);
    }

    // ========================================================================
    // Helper function tests
    // ========================================================================

    #[test]
    fn test_needs_quote_empty() {
        assert!(needs_quote("", "\t"));
    }

    #[test]
    fn test_needs_quote_whitespace() {
        assert!(needs_quote("  padded  ", "\t"));
        assert!(needs_quote(" leading", "\t"));
        assert!(needs_quote("trailing ", "\t"));
    }

    #[test]
    fn test_needs_quote_delimiter() {
        assert!(needs_quote("has\ttab", "\t"));
        assert!(needs_quote("has,comma", ","));
    }

    #[test]
    fn test_needs_quote_special_chars() {
        assert!(needs_quote("has\nnewline", "\t"));
        assert!(needs_quote("has\"quote", "\t"));
        assert!(needs_quote("has\\backslash", "\t"));
    }

    #[test]
    fn test_needs_quote_special_prefix() {
        assert!(needs_quote("@mention", "\t"));
        assert!(needs_quote("#comment", "\t"));
        assert!(needs_quote("-item", "\t"));
    }

    #[test]
    fn test_needs_quote_looks_like_primitive() {
        assert!(needs_quote("true", "\t"));
        assert!(needs_quote("false", "\t"));
        assert!(needs_quote("null", "\t"));
        assert!(needs_quote("42", "\t"));
        assert!(needs_quote("3.14", "\t"));
    }

    #[test]
    fn test_needs_quote_normal_string() {
        assert!(!needs_quote("hello", "\t"));
        assert!(!needs_quote("normal string", "\t"));
    }

    #[test]
    fn test_quote_string() {
        assert_eq!(quote_string("hello"), "\"hello\"");
        assert_eq!(quote_string("say \"hi\""), "\"say \\\"hi\\\"\"");
        assert_eq!(quote_string("line\nbreak"), "\"line\\nbreak\"");
        assert_eq!(quote_string("tab\there"), "\"tab\\there\"");
    }

    #[test]
    fn test_unquote_string() {
        assert_eq!(unquote_string("\"hello\""), "hello");
        assert_eq!(unquote_string("\"say \\\"hi\\\"\""), "say \"hi\"");
        assert_eq!(unquote_string("\"line\\nbreak\""), "line\nbreak");
        assert_eq!(unquote_string("unquoted"), "unquoted");
    }

    #[test]
    fn test_parse_primitive_null() {
        assert_eq!(parse_primitive("null"), Value::Null);
        assert_eq!(parse_primitive("NULL"), Value::Null);
        assert_eq!(parse_primitive(""), Value::Null);
    }

    #[test]
    fn test_parse_primitive_bool() {
        assert_eq!(parse_primitive("true"), Value::Bool(true));
        assert_eq!(parse_primitive("TRUE"), Value::Bool(true));
        assert_eq!(parse_primitive("false"), Value::Bool(false));
        assert_eq!(parse_primitive("FALSE"), Value::Bool(false));
    }

    #[test]
    fn test_parse_primitive_number() {
        assert_eq!(parse_primitive("42"), json!(42));
        assert_eq!(parse_primitive("-17"), json!(-17));
        assert_eq!(parse_primitive("3.15"), json!(3.15));
        assert_eq!(parse_primitive("1e10"), json!(1e10));
    }

    #[test]
    fn test_parse_primitive_string() {
        assert_eq!(parse_primitive("hello"), Value::String("hello".to_string()));
        assert_eq!(
            parse_primitive("\"quoted\""),
            Value::String("quoted".to_string())
        );
    }

    #[test]
    fn test_parse_delimiter() {
        assert_eq!(parse_delimiter("\\t"), "\t");
        assert_eq!(parse_delimiter("\\n"), "\n");
        assert_eq!(parse_delimiter(","), ",");
    }

    #[test]
    fn test_is_uniform_array_empty() {
        let arr: Vec<Value> = vec![];
        let (uniform, _) = is_uniform_array(&arr);
        assert!(!uniform);
    }

    #[test]
    fn test_is_uniform_array_primitives() {
        let arr = vec![json!(1), json!(2), json!(3)];
        let (uniform, _) = is_uniform_array(&arr);
        assert!(!uniform);
    }

    #[test]
    fn test_is_uniform_array_uniform_objects() {
        let arr = vec![json!({"id": 1, "name": "a"}), json!({"id": 2, "name": "b"})];
        let (uniform, fields) = is_uniform_array(&arr);
        assert!(uniform);
        assert!(fields.contains(&"id".to_string()));
        assert!(fields.contains(&"name".to_string()));
    }

    #[test]
    fn test_is_uniform_array_nested_objects() {
        let arr = vec![json!({"id": 1, "nested": {"a": 1}})];
        let (uniform, _) = is_uniform_array(&arr);
        assert!(!uniform); // Contains nested object
    }

    #[test]
    fn test_is_primitive_array() {
        assert!(is_primitive_array(&[json!(1), json!("two"), json!(true)]));
        assert!(!is_primitive_array(&[json!({"a": 1})]));
        assert!(!is_primitive_array(&[json!([1, 2])]));
    }

    #[test]
    fn test_split_row_simple() {
        let row = split_row("a\tb\tc", "\t");
        assert_eq!(row, vec!["a", "b", "c"]);
    }

    #[test]
    fn test_split_row_quoted() {
        let row = split_row("\"a\tb\"\tc", "\t");
        assert_eq!(row, vec!["\"a\tb\"", "c"]);
    }

    #[test]
    fn test_split_row_escaped_quote() {
        let row = split_row("\"a\\\"b\"\tc", "\t");
        assert_eq!(row, vec!["\"a\\\"b\"", "c"]);
    }

    #[test]
    fn test_get_indent_depth() {
        assert_eq!(get_indent_depth("no indent"), 0);
        assert_eq!(get_indent_depth("  one level"), 1);
        assert_eq!(get_indent_depth("    two levels"), 2);
    }

    // ========================================================================
    // Edge cases
    // ========================================================================

    #[test]
    fn test_encode_special_floats() {
        let data = json!({
            "nan": null,  // NaN becomes null in JSON
            "inf": null   // Infinity becomes null in JSON
        });
        let encoded = encode(&data, false).unwrap();
        assert!(encoded.contains("null"));
    }

    #[test]
    fn test_unicode_strings() {
        let data = json!({"text": "Hello 世界 🌍"});
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert_eq!(decoded["text"], "Hello 世界 🌍");
    }

    #[test]
    fn test_long_string() {
        let long = "x".repeat(1000);
        let data = json!({"text": long});
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert_eq!(decoded["text"].as_str().unwrap().len(), 1000);
    }

    #[test]
    fn test_deeply_nested() {
        let data = json!({
            "a": {
                "b": {
                    "c": {
                        "d": "deep"
                    }
                }
            }
        });
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert_eq!(decoded["a"]["b"]["c"]["d"], "deep");
    }

    #[test]
    fn test_array_of_mixed_objects() {
        let data = json!([
            {"type": "a", "value": 1},
            {"type": "b", "extra": "field"}
        ]);
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert!(decoded.is_array());
        assert_eq!(decoded.as_array().unwrap().len(), 2);
    }
}
