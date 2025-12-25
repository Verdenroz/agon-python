//! AGONStruct format encoder/decoder
//!
//! Template-based encoding for repeated object structures.
//!
//! Format structure:
//! ```text
//! @AGON struct
//!
//! @StructName: field1, field2, field3
//!
//! - key: StructName(val1, val2, val3)
//! ```

use regex::Regex;
use serde_json::{Map, Value};
use std::collections::HashMap;
use std::sync::LazyLock;

use crate::error::{AgonError, Result};

const HEADER: &str = "@AGON struct";
const INDENT: &str = "  ";

// Regex patterns
static NUMBER_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?$").unwrap());
static STRUCT_DEF_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^@(\w+)(?:\(([^)]+)\))?:\s*(.*)$").unwrap());
static STRUCT_INST_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^(\w+)\(").unwrap());
static KEY_VALUE_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^([^:]+):\s*(.*)$").unwrap());
static ARRAY_HEADER_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^(\w*)\[(\d+)\]:?").unwrap());

/// Struct definition stored in registry: (fields, optional_fields, parents)
type StructDef = (Vec<String>, Vec<String>, Vec<String>);
type StructRegistry = HashMap<String, StructDef>;

/// Struct definition with name for creation: (name, fields, optional_fields, parents)
#[allow(clippy::type_complexity)]
type StructDefWithName = (String, Vec<String>, Vec<String>, Vec<String>);

/// Encode data to AGONStruct format
pub fn encode(data: &Value, include_header: bool) -> Result<String> {
    let mut lines = Vec::new();

    // Detect shapes and create struct definitions
    let shapes = detect_shapes(data);
    let struct_defs = create_struct_definitions(&shapes, 3, 2);

    // Build registry
    let mut registry = StructRegistry::new();
    for (name, fields, optional, parents) in &struct_defs {
        register_struct(&mut registry, name, fields, optional, parents)?;
    }

    if include_header {
        lines.push(HEADER.to_string());
        lines.push(String::new());
    }

    // Emit struct definitions
    if !struct_defs.is_empty() {
        for (name, fields, optional, parents) in &struct_defs {
            let fields_str: Vec<String> = fields
                .iter()
                .map(|f| {
                    if optional.contains(f) {
                        format!("{}?", f)
                    } else {
                        f.clone()
                    }
                })
                .collect();

            if parents.is_empty() {
                lines.push(format!("@{}: {}", name, fields_str.join(", ")));
            } else {
                lines.push(format!(
                    "@{}({}): {}",
                    name,
                    parents.join(", "),
                    fields_str.join(", ")
                ));
            }
        }
        lines.push(String::new());
    }

    encode_value(data, &mut lines, 0, &registry);

    Ok(lines.join("\n"))
}

/// Decode AGONStruct payload
pub fn decode(payload: &str) -> Result<Value> {
    let lines: Vec<&str> = payload.lines().collect();
    if lines.is_empty() {
        return Err(AgonError::DecodingError("Empty payload".to_string()));
    }

    let mut idx = 0;

    // Parse header
    let header_line = lines[idx].trim();
    if !header_line.starts_with("@AGON struct") {
        return Err(AgonError::DecodingError(format!(
            "Invalid header: {}",
            header_line
        )));
    }
    idx += 1;

    // Parse struct definitions
    let mut registry = StructRegistry::new();
    while idx < lines.len() {
        let line = lines[idx].trim();
        if line.is_empty() {
            idx += 1;
            continue;
        }
        if !line.starts_with('@') {
            break;
        }
        if let Some(parsed) = parse_struct_def(line) {
            let (name, fields, optional, parents) = parsed;
            register_struct(&mut registry, &name, &fields, &optional, &parents)?;
        }
        idx += 1;
    }

    // Skip blank lines
    while idx < lines.len() && lines[idx].trim().is_empty() {
        idx += 1;
    }

    if idx >= lines.len() {
        return Ok(Value::Null);
    }

    let (result, _) = decode_value(&lines, idx, 0, &registry)?;
    Ok(result)
}

// ============================================================================
// Shape detection
// ============================================================================

/// Shape signature: sorted list of field names
type Shape = Vec<String>;

fn get_shape(obj: &Map<String, Value>) -> Shape {
    let mut fields: Vec<String> = obj
        .iter()
        .filter(|(_, v)| !v.is_object() && !v.is_array())
        .map(|(k, _)| k.clone())
        .collect();
    fields.sort();
    fields
}

fn detect_shapes(data: &Value) -> HashMap<Shape, usize> {
    let mut shapes = HashMap::new();
    collect_shapes(data, &mut shapes);
    shapes
}

fn collect_shapes(data: &Value, shapes: &mut HashMap<Shape, usize>) {
    match data {
        Value::Array(arr) => {
            for item in arr {
                collect_shapes(item, shapes);
            }
        }
        Value::Object(obj) => {
            let shape = get_shape(obj);
            if !shape.is_empty() {
                *shapes.entry(shape).or_insert(0) += 1;
            }
            for v in obj.values() {
                collect_shapes(v, shapes);
            }
        }
        _ => {}
    }
}

fn create_struct_definitions(
    shapes: &HashMap<Shape, usize>,
    min_occurrences: usize,
    min_fields: usize,
) -> Vec<StructDefWithName> {
    let mut defs = Vec::new();
    let mut used_names: std::collections::HashSet<String> = std::collections::HashSet::new();

    for (shape, count) in shapes {
        if *count >= min_occurrences && shape.len() >= min_fields {
            let name = generate_struct_name(shape, &mut used_names);
            defs.push((name, shape.clone(), vec![], vec![]));
        }
    }

    defs
}

/// Generate a struct name from field names
/// Takes first letter of each field (up to 4), adds counter on collision
fn generate_struct_name(
    fields: &[String],
    used_names: &mut std::collections::HashSet<String>,
) -> String {
    // Take first letter of each field, truncate to 4 chars max
    let base_name: String = fields
        .iter()
        .filter_map(|f| f.chars().next())
        .map(|c| c.to_ascii_uppercase())
        .take(4)
        .collect();

    // Fallback if empty
    let base_name = if base_name.is_empty() {
        "S".to_string()
    } else {
        base_name
    };

    // Add counter on collision
    let mut name = base_name.clone();
    let mut counter = 1;
    while used_names.contains(&name) {
        counter += 1;
        name = format!("{}{}", base_name, counter);
    }
    used_names.insert(name.clone());
    name
}

fn register_struct(
    registry: &mut StructRegistry,
    name: &str,
    fields: &[String],
    optional: &[String],
    parents: &[String],
) -> Result<()> {
    let mut all_fields = Vec::new();

    // Resolve parent fields
    for parent_name in parents {
        if let Some((parent_fields, _, _)) = registry.get(parent_name) {
            for f in parent_fields {
                if !all_fields.contains(f) {
                    all_fields.push(f.clone());
                }
            }
        }
    }

    // Add own fields
    for f in fields {
        if !all_fields.contains(f) {
            all_fields.push(f.clone());
        }
    }

    registry.insert(
        name.to_string(),
        (all_fields, optional.to_vec(), parents.to_vec()),
    );
    Ok(())
}

// ============================================================================
// Encoding helpers
// ============================================================================

fn format_primitive(val: &Value) -> String {
    match val {
        Value::Null => "null".to_string(),
        Value::Bool(b) => if *b { "true" } else { "false" }.to_string(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => {
            // Quote if contains special chars or could be parsed as another type
            if needs_quote(s) {
                format!(
                    "\"{}\"",
                    s.replace('\\', "\\\\")
                        .replace('"', "\\\"")
                        .replace('\n', "\\n")
                )
            } else {
                s.clone()
            }
        }
        _ => serde_json::to_string(val).unwrap_or_default(),
    }
}

/// Check if a string needs quoting to preserve its type
fn needs_quote(s: &str) -> bool {
    if s.is_empty() {
        return true;
    }
    // Strings with leading/trailing whitespace need quoting
    if s != s.trim() {
        return true;
    }
    // Struct format special chars
    // ':' is included to avoid ambiguity with inline key-value parsing in lists.
    if s.contains(',')
        || s.contains(':')
        || s.contains('(')
        || s.contains(')')
        || s.contains('\n')
        || s.contains('\\')
        || s.contains('"')
    {
        return true;
    }
    // Tree chars and special prefixes
    if s.starts_with('@') || s.starts_with('#') || s.starts_with('-') {
        return true;
    }
    // Boolean/null keywords
    let lower = s.to_lowercase();
    if lower == "true" || lower == "false" || lower == "null" {
        return true;
    }
    // Looks like a number - needs quoting to preserve string type
    if s.parse::<i64>().is_ok() || s.parse::<f64>().is_ok() {
        return true;
    }
    false
}

fn find_matching_struct(obj: &Map<String, Value>, registry: &StructRegistry) -> Option<String> {
    // Object must have only primitive values to use struct encoding
    // If it has nested objects/arrays, we can't use struct templates
    for v in obj.values() {
        if v.is_object() || v.is_array() {
            return None;
        }
    }

    let shape = get_shape(obj);
    if shape.is_empty() {
        return None;
    }

    for (name, (fields, _, _)) in registry {
        // Check if all required fields match
        let mut sorted_fields = fields.clone();
        sorted_fields.sort();
        if sorted_fields == shape {
            return Some(name.clone());
        }
    }
    None
}

fn encode_value(val: &Value, lines: &mut Vec<String>, depth: usize, registry: &StructRegistry) {
    let indent = INDENT.repeat(depth);

    match val {
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {
            lines.push(format!("{}{}", indent, format_primitive(val)));
        }
        Value::Array(arr) => {
            encode_array(arr, lines, depth, registry);
        }
        Value::Object(obj) => {
            encode_object(obj, lines, depth, registry, None);
        }
    }
}

fn encode_array(arr: &[Value], lines: &mut Vec<String>, depth: usize, registry: &StructRegistry) {
    let indent = INDENT.repeat(depth);

    if arr.is_empty() {
        lines.push(format!("{}[0]:", indent));
        return;
    }

    lines.push(format!("{}[{}]:", indent, arr.len()));

    for item in arr {
        if let Some(obj) = item.as_object() {
            // Only use struct template if ALL fields are primitives (struct covers everything)
            // If object has nested objects/arrays, use list item format to preserve them
            let has_nested = obj.values().any(|v| v.is_object() || v.is_array());

            if !has_nested {
                if let Some(struct_name) = find_matching_struct(obj, registry) {
                    if let Some((fields, _, _)) = registry.get(&struct_name) {
                        let values: Vec<String> = fields
                            .iter()
                            .map(|f| obj.get(f).map(format_primitive).unwrap_or_default())
                            .collect();
                        lines.push(format!(
                            "{}  - {}({})",
                            indent,
                            struct_name,
                            values.join(", ")
                        ));
                        continue;
                    }
                }
            }
            encode_list_item(obj, lines, depth + 1, registry);
        } else {
            lines.push(format!("{}  - {}", indent, format_primitive(item)));
        }
    }
}

fn encode_list_item(
    obj: &Map<String, Value>,
    lines: &mut Vec<String>,
    depth: usize,
    registry: &StructRegistry,
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

        // Check if value can use a struct
        if let Some(nested_obj) = v.as_object() {
            if let Some(struct_name) = find_matching_struct(nested_obj, registry) {
                if let Some((fields, _, _)) = registry.get(&struct_name) {
                    let values: Vec<String> = fields
                        .iter()
                        .map(|f| nested_obj.get(f).map(format_primitive).unwrap_or_default())
                        .collect();
                    lines.push(format!(
                        "{}{}: {}({})",
                        prefix,
                        k,
                        struct_name,
                        values.join(", ")
                    ));
                    continue;
                }
            }
        }

        match v {
            Value::Object(nested) => {
                lines.push(format!("{}{}:", prefix, k));
                encode_object(nested, lines, depth + 2, registry, None);
            }
            Value::Array(arr) => {
                lines.push(format!("{}{}:", prefix, k));
                encode_array(arr, lines, depth + 2, registry);
            }
            _ => {
                lines.push(format!("{}{}: {}", prefix, k, format_primitive(v)));
            }
        }
    }
}

fn encode_object(
    obj: &Map<String, Value>,
    lines: &mut Vec<String>,
    depth: usize,
    registry: &StructRegistry,
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
        // Check if value can use a struct
        if let Some(nested_obj) = v.as_object() {
            if let Some(struct_name) = find_matching_struct(nested_obj, registry) {
                if let Some((fields, _, _)) = registry.get(&struct_name) {
                    let values: Vec<String> = fields
                        .iter()
                        .map(|f| nested_obj.get(f).map(format_primitive).unwrap_or_default())
                        .collect();
                    lines.push(format!(
                        "{}{}: {}({})",
                        actual_indent,
                        k,
                        struct_name,
                        values.join(", ")
                    ));
                    continue;
                }
            }
        }

        match v {
            Value::Object(nested) => {
                encode_object(nested, lines, actual_depth, registry, Some(k));
            }
            Value::Array(arr) => {
                lines.push(format!("{}{}", actual_indent, k));
                encode_array(arr, lines, actual_depth + 1, registry);
            }
            _ => {
                lines.push(format!("{}{}: {}", actual_indent, k, format_primitive(v)));
            }
        }
    }
}

// ============================================================================
// Decoding helpers
// ============================================================================

fn parse_struct_def(line: &str) -> Option<StructDefWithName> {
    let caps = STRUCT_DEF_RE.captures(line)?;

    let name = caps.get(1)?.as_str().to_string();
    let parents: Vec<String> = caps
        .get(2)
        .map(|m| {
            m.as_str()
                .split(',')
                .map(|s| s.trim().to_string())
                .collect()
        })
        .unwrap_or_default();
    let fields_str = caps.get(3)?.as_str();

    let mut fields = Vec::new();
    let mut optional = Vec::new();

    for field in fields_str.split(',') {
        let field = field.trim();
        if field.is_empty() {
            continue;
        }
        if let Some(name) = field.strip_suffix('?') {
            fields.push(name.to_string());
            optional.push(name.to_string());
        } else {
            fields.push(field.to_string());
        }
    }

    Some((name, fields, optional, parents))
}

fn parse_primitive(s: &str) -> Value {
    let s = s.trim();
    if s.is_empty() {
        return Value::Null;
    }

    // Quoted string
    if s.starts_with('"') && s.ends_with('"') {
        let inner = &s[1..s.len() - 1];
        return Value::String(
            inner
                .replace("\\n", "\n")
                .replace("\\\"", "\"")
                .replace("\\\\", "\\"),
        );
    }

    // Boolean/null
    match s.to_lowercase().as_str() {
        "null" => return Value::Null,
        "true" => return Value::Bool(true),
        "false" => return Value::Bool(false),
        _ => {}
    }

    // Number
    if NUMBER_RE.is_match(s) {
        if s.contains('.') || s.to_lowercase().contains('e') {
            if let Ok(f) = s.parse::<f64>() {
                if let Some(n) = serde_json::Number::from_f64(f) {
                    return Value::Number(n);
                }
            }
        } else if let Ok(i) = s.parse::<i64>() {
            return Value::Number(i.into());
        }
    }

    Value::String(s.to_string())
}

fn get_indent_depth(line: &str) -> usize {
    let stripped = line.trim_start_matches(' ');
    let spaces = line.len() - stripped.len();
    spaces / 2
}

fn parse_struct_instance(s: &str, registry: &StructRegistry) -> Option<Value> {
    let caps = STRUCT_INST_RE.captures(s)?;
    let name = caps.get(1)?.as_str();

    let (fields, _, _) = registry.get(name)?;

    // Find the closing paren
    let start = s.find('(')? + 1;
    let end = s.rfind(')')?;
    let values_str = &s[start..end];

    // Split values (respecting nested parens and quotes)
    let values = split_struct_values(values_str);

    let mut obj = Map::new();
    for (i, field) in fields.iter().enumerate() {
        if let Some(val_str) = values.get(i) {
            // Recursively parse struct instances
            let val = if let Some(nested) = parse_struct_instance(val_str.trim(), registry) {
                nested
            } else {
                parse_primitive(val_str)
            };
            obj.insert(field.clone(), val);
        }
    }

    Some(Value::Object(obj))
}

fn split_struct_values(s: &str) -> Vec<String> {
    let mut values = Vec::new();
    let mut current = String::new();
    let mut paren_depth = 0;
    let mut in_quote = false;

    for c in s.chars() {
        match c {
            '"' if !in_quote => in_quote = true,
            '"' if in_quote => in_quote = false,
            '(' if !in_quote => paren_depth += 1,
            ')' if !in_quote => paren_depth -= 1,
            ',' if !in_quote && paren_depth == 0 => {
                values.push(current.trim().to_string());
                current = String::new();
                continue;
            }
            _ => {}
        }
        current.push(c);
    }

    if !current.is_empty() {
        values.push(current.trim().to_string());
    }

    values
}

fn decode_value(
    lines: &[&str],
    idx: usize,
    depth: usize,
    registry: &StructRegistry,
) -> Result<(Value, usize)> {
    if idx >= lines.len() {
        return Ok((Value::Null, idx));
    }

    let line = lines[idx];
    let stripped = line.trim();

    if stripped.is_empty() {
        return decode_value(lines, idx + 1, depth, registry);
    }

    // Check for array
    if let Some(caps) = ARRAY_HEADER_RE.captures(stripped) {
        let name = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        if name.is_empty() {
            return decode_array(lines, idx, depth, registry);
        }
    }

    // Check for list item
    if stripped.starts_with("- ") {
        return decode_array_from_items(lines, idx, depth, registry);
    }

    // Check for key: value
    if KEY_VALUE_RE.is_match(stripped) {
        return decode_object(lines, idx, depth, registry);
    }

    // Check for bare identifier followed by array (object with array value)
    if is_bare_identifier(stripped) {
        // Look ahead to see if next non-empty line is an array header
        let mut next_idx = idx + 1;
        while next_idx < lines.len() && lines[next_idx].trim().is_empty() {
            next_idx += 1;
        }
        if next_idx < lines.len() && ARRAY_HEADER_RE.is_match(lines[next_idx].trim()) {
            // This is an object with a key pointing to an array
            return decode_object(lines, idx, depth, registry);
        }
    }

    // Single value
    let val = if let Some(struct_val) = parse_struct_instance(stripped, registry) {
        struct_val
    } else {
        parse_primitive(stripped)
    };

    Ok((val, idx + 1))
}

fn decode_array(
    lines: &[&str],
    idx: usize,
    depth: usize,
    registry: &StructRegistry,
) -> Result<(Value, usize)> {
    let line = lines[idx].trim();
    let caps = ARRAY_HEADER_RE.captures(line).unwrap();
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
        if line.trim().is_empty() {
            idx += 1;
            continue;
        }

        let line_depth = get_indent_depth(line);
        if line_depth < base_depth {
            break;
        }

        let stripped = line.trim();
        if let Some(item_str) = stripped.strip_prefix("- ") {
            let content = item_str.trim();
            // Check struct instance FIRST (struct values may contain ':' which matches KEY_VALUE_RE)
            if let Some(struct_val) = parse_struct_instance(content, registry) {
                result.push(struct_val);
                idx += 1;
            } else if is_quoted_string(content) {
                // If this is a quoted string list item, treat it as a primitive.
                // This avoids ambiguity with inline object syntax when the string
                // contains ':' (e.g. "keyword match: foo").
                result.push(parse_primitive(content));
                idx += 1;
            } else if KEY_VALUE_RE.is_match(content) {
                let (obj, new_idx) = decode_list_item(lines, idx, base_depth, registry)?;
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

fn decode_array_from_items(
    lines: &[&str],
    idx: usize,
    _depth: usize,
    registry: &StructRegistry,
) -> Result<(Value, usize)> {
    let mut result = Vec::new();
    let base_depth = get_indent_depth(lines[idx]);
    let mut idx = idx;

    while idx < lines.len() {
        let line = lines[idx];
        if line.trim().is_empty() {
            idx += 1;
            continue;
        }

        let line_depth = get_indent_depth(line);
        if line_depth < base_depth {
            break;
        }

        let stripped = line.trim();
        if let Some(item_str) = stripped.strip_prefix("- ") {
            let content = item_str.trim();
            // Check struct instance first
            if let Some(struct_val) = parse_struct_instance(content, registry) {
                result.push(struct_val);
                idx += 1;
            } else if is_quoted_string(content) {
                // Quoted strings should be treated as primitives, not key-value pairs
                result.push(parse_primitive(content));
                idx += 1;
            } else if KEY_VALUE_RE.is_match(content) {
                let (obj, new_idx) = decode_list_item(lines, idx, base_depth, registry)?;
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

    Ok((Value::Array(result), idx))
}

/// Check if a string is a quoted string (starts and ends with double quotes)
fn is_quoted_string(s: &str) -> bool {
    s.len() >= 2 && s.starts_with('"') && s.ends_with('"')
}

fn decode_list_item(
    lines: &[&str],
    idx: usize,
    base_depth: usize,
    registry: &StructRegistry,
) -> Result<(Value, usize)> {
    let mut obj = Map::new();
    let item_depth = base_depth;

    let first_line = lines[idx].trim();
    let first_content = first_line.strip_prefix("- ").unwrap_or(first_line).trim();

    let mut idx = idx;

    if let Some(caps) = KEY_VALUE_RE.captures(first_content) {
        let key = caps.get(1).map(|m| m.as_str()).unwrap_or("").trim();
        let val_str = caps.get(2).map(|m| m.as_str()).unwrap_or("").trim();

        if !val_str.is_empty() {
            let val = if let Some(struct_val) = parse_struct_instance(val_str, registry) {
                struct_val
            } else {
                parse_primitive(val_str)
            };
            obj.insert(key.to_string(), val);
            idx += 1;
        } else {
            idx += 1;
            if idx < lines.len() {
                let next_depth = get_indent_depth(lines[idx]);
                if next_depth > item_depth + 1 {
                    let (nested, new_idx) = decode_value(lines, idx, next_depth, registry)?;
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

        // Check for new list item - this is a boundary, not a continuation
        if stripped.starts_with("- ") {
            break;
        }

        if let Some(caps) = KEY_VALUE_RE.captures(stripped) {
            let key = caps.get(1).map(|m| m.as_str()).unwrap_or("").trim();
            let val_str = caps.get(2).map(|m| m.as_str()).unwrap_or("").trim();

            if !val_str.is_empty() {
                let val = if let Some(struct_val) = parse_struct_instance(val_str, registry) {
                    struct_val
                } else {
                    parse_primitive(val_str)
                };
                obj.insert(key.to_string(), val);
                idx += 1;
            } else {
                idx += 1;
                if idx < lines.len() {
                    let next_depth = get_indent_depth(lines[idx]);
                    if next_depth > line_depth {
                        let (nested, new_idx) = decode_value(lines, idx, next_depth, registry)?;
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
        } else if is_bare_identifier(stripped) {
            // Bare key (no colon) - check if next line is an array
            let key = stripped.to_string();
            idx += 1;

            // Skip blank lines
            while idx < lines.len() && lines[idx].trim().is_empty() {
                idx += 1;
            }

            if idx < lines.len() {
                let next_line = lines[idx].trim();
                // Check if next line starts an array
                if ARRAY_HEADER_RE.is_match(next_line) {
                    let (arr, new_idx) = decode_array(lines, idx, line_depth, registry)?;
                    obj.insert(key, arr);
                    idx = new_idx;
                } else {
                    // Not an array, treat key as having null/empty value
                    obj.insert(key, Value::Null);
                }
            } else {
                obj.insert(key, Value::Null);
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
    registry: &StructRegistry,
) -> Result<(Value, usize)> {
    let mut result = Map::new();
    let base_depth = get_indent_depth(lines[idx]);
    let mut idx = idx;

    while idx < lines.len() {
        let line = lines[idx];
        if line.trim().is_empty() {
            idx += 1;
            continue;
        }

        let line_depth = get_indent_depth(line);
        if line_depth < base_depth {
            break;
        }

        let stripped = line.trim();

        if let Some(caps) = KEY_VALUE_RE.captures(stripped) {
            let key = caps.get(1).map(|m| m.as_str()).unwrap_or("").trim();
            let val_str = caps.get(2).map(|m| m.as_str()).unwrap_or("").trim();

            if !val_str.is_empty() {
                let val = if let Some(struct_val) = parse_struct_instance(val_str, registry) {
                    struct_val
                } else {
                    parse_primitive(val_str)
                };
                result.insert(key.to_string(), val);
                idx += 1;
            } else {
                idx += 1;
                if idx < lines.len() {
                    let next_depth = get_indent_depth(lines[idx]);
                    if next_depth > line_depth {
                        let (nested, new_idx) = decode_value(lines, idx, next_depth, registry)?;
                        result.insert(key.to_string(), nested);
                        idx = new_idx;
                    } else {
                        result.insert(key.to_string(), Value::Object(Map::new()));
                    }
                } else {
                    // End of file - still insert empty object
                    result.insert(key.to_string(), Value::Object(Map::new()));
                }
            }
        } else if is_bare_identifier(stripped) {
            // Bare key (no colon) - check if next line is an array
            let key = stripped.to_string();
            idx += 1;

            // Skip blank lines
            while idx < lines.len() && lines[idx].trim().is_empty() {
                idx += 1;
            }

            if idx < lines.len() {
                let next_line = lines[idx].trim();
                // Check if next line starts an array
                if ARRAY_HEADER_RE.is_match(next_line) {
                    let (arr, new_idx) = decode_array(lines, idx, line_depth, registry)?;
                    result.insert(key, arr);
                    idx = new_idx;
                } else {
                    // Not an array, treat key as having null/empty value
                    result.insert(key, Value::Null);
                }
            } else {
                result.insert(key, Value::Null);
            }
        } else {
            break;
        }
    }

    Ok((Value::Object(result), idx))
}

/// Check if a string is a bare identifier (valid key name without colon)
fn is_bare_identifier(s: &str) -> bool {
    if s.is_empty() {
        return false;
    }
    // Must not contain colon (that would be key:value)
    if s.contains(':') {
        return false;
    }
    // Must not be an array header
    if ARRAY_HEADER_RE.is_match(s) {
        return false;
    }
    // Must not start with special chars
    if s.starts_with('-') || s.starts_with('@') || s.starts_with('#') {
        return false;
    }
    // Should be a valid identifier (alphanumeric + underscore, starting with letter)
    let first = s.chars().next().unwrap();
    if !first.is_alphabetic() && first != '_' {
        return false;
    }
    s.chars().all(|c| c.is_alphanumeric() || c == '_')
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // ========================================================================
    // Encoding tests
    // ========================================================================

    #[test]
    fn test_encode_with_structs() {
        let data = json!({
            "items": [
                {"fmt": "1.00", "raw": 1.0},
                {"fmt": "2.00", "raw": 2.0},
                {"fmt": "3.00", "raw": 3.0}
            ]
        });
        let encoded = encode(&data, true).unwrap();
        assert!(encoded.starts_with("@AGON struct"));
    }

    #[test]
    fn test_encode_with_header() {
        let data = json!({"name": "test"});
        let encoded = encode(&data, true).unwrap();
        assert!(encoded.starts_with("@AGON struct"));
    }

    #[test]
    fn test_encode_without_header() {
        let data = json!({"name": "test"});
        let encoded = encode(&data, false).unwrap();
        assert!(!encoded.starts_with("@AGON"));
    }

    #[test]
    fn test_encode_primitives() {
        let data = json!({
            "string": "hello",
            "number": 42,
            "bool_true": true,
            "null_val": null
        });
        let encoded = encode(&data, false).unwrap();
        assert!(encoded.contains("string: hello"));
        assert!(encoded.contains("number: 42"));
        assert!(encoded.contains("bool_true: true"));
        assert!(encoded.contains("null_val: null"));
    }

    #[test]
    fn test_encode_repeated_shapes_creates_struct() {
        // Three occurrences of same shape should create a struct
        let data = json!({
            "price": {"fmt": "100.00", "raw": 100.0},
            "change": {"fmt": "+5.00", "raw": 5.0},
            "volume": {"fmt": "1M", "raw": 1000000}
        });
        let encoded = encode(&data, false).unwrap();
        // Should have struct definition
        assert!(encoded.contains("@") && encoded.contains(":"));
    }

    #[test]
    fn test_encode_empty_array() {
        let data = json!({"items": []});
        let encoded = encode(&data, false).unwrap();
        assert!(encoded.contains("[0]:"));
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
        let result = decode("@AGON struct\n\n").unwrap();
        assert!(result.is_null());
    }

    #[test]
    fn test_decode_simple_struct_instance() {
        let payload = "@AGON struct\n\n@FR: fmt, raw\n\nprice: FR(\"100.00\", 100.0)";
        let decoded = decode(payload).unwrap();
        assert_eq!(decoded["price"]["fmt"], "100.00");
        assert_eq!(decoded["price"]["raw"], 100.0);
    }

    #[test]
    fn test_decode_multiple_struct_instances() {
        let payload =
            "@AGON struct\n\n@FR: fmt, raw\n\nprice: FR(\"100\", 100)\nchange: FR(\"5\", 5)";
        let decoded = decode(payload).unwrap();
        assert_eq!(decoded["price"]["fmt"], "100");
        assert_eq!(decoded["change"]["fmt"], "5");
    }

    #[test]
    fn test_decode_inherited_struct() {
        let payload =
            "@AGON struct\n\n@FR: fmt, raw\n@FRC(FR): currency\n\nprice: FRC(\"100\", 100, USD)";
        let decoded = decode(payload).unwrap();
        assert_eq!(decoded["price"]["fmt"], "100");
        assert_eq!(decoded["price"]["raw"], 100);
        assert_eq!(decoded["price"]["currency"], "USD");
    }

    #[test]
    fn test_decode_optional_field_present() {
        let payload =
            "@AGON struct\n\n@Quote: symbol, price, volume?\n\nstock: Quote(AAPL, 150.0, 1000000)";
        let decoded = decode(payload).unwrap();
        assert_eq!(decoded["stock"]["symbol"], "AAPL");
        assert_eq!(decoded["stock"]["price"], 150.0);
        assert_eq!(decoded["stock"]["volume"], 1000000);
    }

    #[test]
    fn test_decode_optional_field_omitted() {
        let payload = "@AGON struct\n\n@Quote: symbol, price, volume?\n\nstock: Quote(AAPL, 150.0)";
        let decoded = decode(payload).unwrap();
        assert_eq!(decoded["stock"]["symbol"], "AAPL");
        assert_eq!(decoded["stock"]["price"], 150.0);
        // Optional field should be absent
        assert!(decoded["stock"].get("volume").is_none() || decoded["stock"]["volume"].is_null());
    }

    // ========================================================================
    // Roundtrip tests
    // ========================================================================

    #[test]
    fn test_roundtrip_financial_data() {
        let data = json!({
            "symbol": "AAPL",
            "price": {"fmt": "150.00", "raw": 150.0},
            "change": {"fmt": "+2.50", "raw": 2.5},
            "volume": {"fmt": "1M", "raw": 1000000}
        });
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert_eq!(decoded["symbol"], "AAPL");
        assert_eq!(decoded["price"]["fmt"], "150.00");
    }

    #[test]
    fn test_roundtrip_array_of_structs() {
        let data = json!([
            {"fmt": "1", "raw": 1},
            {"fmt": "2", "raw": 2},
            {"fmt": "3", "raw": 3}
        ]);
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert!(decoded.is_array());
        assert_eq!(decoded.as_array().unwrap().len(), 3);
    }

    #[test]
    fn test_roundtrip_nested_object() {
        let data = json!({
            "quote": {
                "price": {"fmt": "100", "raw": 100.0},
                "change": {"fmt": "5", "raw": 5.0},
                "volume": {"fmt": "1M", "raw": 1000000}
            }
        });
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert!(decoded["quote"].is_object());
    }

    // ========================================================================
    // Parse struct definition tests
    // ========================================================================

    #[test]
    fn test_parse_struct_def() {
        let line = "@FR: fmt, raw";
        let (name, fields, optional, parents) = parse_struct_def(line).unwrap();
        assert_eq!(name, "FR");
        assert_eq!(fields, vec!["fmt", "raw"]);
        assert!(optional.is_empty());
        assert!(parents.is_empty());
    }

    #[test]
    fn test_parse_struct_def_with_optional() {
        let line = "@Quote: symbol, price, volume?";
        let (name, fields, optional, _) = parse_struct_def(line).unwrap();
        assert_eq!(name, "Quote");
        assert_eq!(fields, vec!["symbol", "price", "volume"]);
        assert_eq!(optional, vec!["volume"]);
    }

    #[test]
    fn test_parse_struct_def_with_parent() {
        let line = "@FRC(FR): currency";
        let (name, fields, _, parents) = parse_struct_def(line).unwrap();
        assert_eq!(name, "FRC");
        assert_eq!(fields, vec!["currency"]);
        assert_eq!(parents, vec!["FR"]);
    }

    // ========================================================================
    // Helper function tests
    // ========================================================================

    #[test]
    fn test_needs_quote_empty() {
        assert!(needs_quote(""));
    }

    #[test]
    fn test_needs_quote_whitespace() {
        assert!(needs_quote("  padded  "));
        assert!(needs_quote(" leading"));
    }

    #[test]
    fn test_needs_quote_special_chars() {
        assert!(needs_quote("has,comma"));
        assert!(needs_quote("has:colon"));
        assert!(needs_quote("has(paren)"));
        assert!(needs_quote("has\"quote"));
    }

    #[test]
    fn test_needs_quote_special_prefix() {
        assert!(needs_quote("@mention"));
        assert!(needs_quote("#comment"));
        assert!(needs_quote("-item"));
    }

    #[test]
    fn test_needs_quote_primitives() {
        assert!(needs_quote("true"));
        assert!(needs_quote("false"));
        assert!(needs_quote("null"));
        assert!(needs_quote("42"));
        assert!(needs_quote("3.14"));
    }

    #[test]
    fn test_needs_quote_normal_string() {
        assert!(!needs_quote("hello"));
        assert!(!needs_quote("normal string"));
    }

    #[test]
    fn test_format_primitive() {
        assert_eq!(format_primitive(&Value::Null), "null");
        assert_eq!(format_primitive(&Value::Bool(true)), "true");
        assert_eq!(format_primitive(&Value::Bool(false)), "false");
        assert_eq!(format_primitive(&json!(42)), "42");
        assert_eq!(format_primitive(&json!("hello")), "hello");
        assert_eq!(format_primitive(&json!("42")), "\"42\""); // Quoted to preserve string type
    }

    #[test]
    fn test_get_shape() {
        let obj = json!({"a": 1, "b": "two", "nested": {"x": 1}})
            .as_object()
            .unwrap()
            .clone();
        let shape = get_shape(&obj);
        // Should only include primitive fields
        assert!(shape.contains(&"a".to_string()));
        assert!(shape.contains(&"b".to_string()));
        assert!(!shape.contains(&"nested".to_string())); // Nested object excluded
    }

    #[test]
    fn test_detect_shapes() {
        let data = json!([
            {"a": 1, "b": 2},
            {"a": 3, "b": 4},
            {"a": 5, "b": 6}
        ]);
        let shapes = detect_shapes(&data);
        // Should have one shape with count 3
        assert!(!shapes.is_empty());
        let shape = vec!["a".to_string(), "b".to_string()];
        assert_eq!(shapes.get(&shape), Some(&3));
    }

    #[test]
    fn test_generate_struct_name() {
        let mut used = std::collections::HashSet::new();
        let name = generate_struct_name(&["fmt".to_string(), "raw".to_string()], &mut used);
        assert_eq!(name, "FR");
        assert!(used.contains(&name));
    }

    #[test]
    fn test_generate_struct_name_collision() {
        let mut used = std::collections::HashSet::new();
        used.insert("FR".to_string());
        let name = generate_struct_name(&["fmt".to_string(), "raw".to_string()], &mut used);
        assert_eq!(name, "FR2"); // Should add counter
    }

    #[test]
    fn test_find_matching_struct() {
        let mut registry = StructRegistry::new();
        registry.insert(
            "FR".to_string(),
            (vec!["fmt".to_string(), "raw".to_string()], vec![], vec![]),
        );

        let obj = json!({"fmt": "100", "raw": 100})
            .as_object()
            .unwrap()
            .clone();
        let matched = find_matching_struct(&obj, &registry);
        assert_eq!(matched, Some("FR".to_string()));
    }

    #[test]
    fn test_find_matching_struct_no_match() {
        let mut registry = StructRegistry::new();
        registry.insert(
            "FR".to_string(),
            (vec!["fmt".to_string(), "raw".to_string()], vec![], vec![]),
        );

        let obj = json!({"x": 1, "y": 2}).as_object().unwrap().clone();
        let matched = find_matching_struct(&obj, &registry);
        assert!(matched.is_none());
    }

    #[test]
    fn test_find_matching_struct_with_nested_returns_none() {
        let mut registry = StructRegistry::new();
        registry.insert(
            "FR".to_string(),
            (vec!["fmt".to_string(), "raw".to_string()], vec![], vec![]),
        );

        // Object with nested value - should not match struct
        let obj = json!({"fmt": "100", "raw": 100, "nested": {"a": 1}})
            .as_object()
            .unwrap()
            .clone();
        let matched = find_matching_struct(&obj, &registry);
        assert!(matched.is_none());
    }

    // ========================================================================
    // Edge cases
    // ========================================================================

    #[test]
    fn test_unicode_strings() {
        let data = json!({"text": "Hello 世界"});
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert_eq!(decoded["text"], "Hello 世界");
    }

    #[test]
    fn test_quoted_string_with_colon() {
        // Strings containing ':' should be quoted and preserved
        let data = json!(["keyword match: for, object, return", "plain text"]);
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert!(decoded.is_array());
        let arr = decoded.as_array().unwrap();
        assert_eq!(arr[0], "keyword match: for, object, return");
        assert_eq!(arr[1], "plain text");
    }

    #[test]
    fn test_struct_with_boolean_values() {
        let payload = "@AGON struct\n\n@Flags: a, b\n\nitem: Flags(true, false)";
        let decoded = decode(payload).unwrap();
        assert_eq!(decoded["item"]["a"], true);
        assert_eq!(decoded["item"]["b"], false);
    }

    #[test]
    fn test_struct_with_null_values() {
        let payload = "@AGON struct\n\n@Pair: a, b\n\nitem: Pair(, test)";
        let decoded = decode(payload).unwrap();
        assert!(decoded["item"]["a"].is_null());
        assert_eq!(decoded["item"]["b"], "test");
    }

    #[test]
    fn test_struct_with_numeric_values() {
        let payload = "@AGON struct\n\n@Nums: int_val, float_val\n\nitem: Nums(42, 3.15)";
        let decoded = decode(payload).unwrap();
        assert_eq!(decoded["item"]["int_val"], 42);
        assert_eq!(decoded["item"]["float_val"], 3.15);
    }

    #[test]
    fn test_deeply_nested_with_structs() {
        let data = json!({
            "level1": {
                "level2": {
                    "a": {"fmt": "1", "raw": 1},
                    "b": {"fmt": "2", "raw": 2},
                    "c": {"fmt": "3", "raw": 3}
                }
            }
        });
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert!(decoded["level1"]["level2"].is_object());
    }
}
