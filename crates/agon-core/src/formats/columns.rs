//! AGONColumns format encoder/decoder
//!
//! Columnar encoding with type clustering for wide tables.
//!
//! Format structure:
//!     @AGON columns
//!     name[N]
//!     ├ field1: val1<delim>val2<delim>...
//!     ├ field2: val1<delim>val2<delim>...
//!     └ fieldN: val1<delim>val2<delim>...

use serde_json::{Map, Value};

use crate::error::{AgonError, Result};

const HEADER: &str = "@AGON columns";
const DEFAULT_DELIMITER: &str = "\t";
const INDENT: &str = "  ";

/// Encode data to AGONColumns format
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

/// Decode AGONColumns payload
pub fn decode(payload: &str) -> Result<Value> {
    let lines: Vec<&str> = payload.lines().collect();
    if lines.is_empty() {
        return Err(AgonError::DecodingError("Empty payload".to_string()));
    }

    let mut idx = 0;

    // Parse header
    let header_line = lines[idx].trim();
    if !header_line.starts_with("@AGON columns") {
        return Err(AgonError::DecodingError(format!(
            "Invalid header: {}",
            header_line
        )));
    }
    idx += 1;

    // Skip blank lines
    while idx < lines.len() && lines[idx].trim().is_empty() {
        idx += 1;
    }

    if idx >= lines.len() {
        return Ok(Value::Null);
    }

    let (result, _) = decode_value(&lines, idx, 0, DEFAULT_DELIMITER)?;
    Ok(result)
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
            // Quote if contains delimiter, special chars, or could be parsed as another type
            if needs_quote(s) {
                format!(
                    "\"{}\"",
                    s.replace('\\', "\\\\")
                        .replace('"', "\\\"")
                        .replace('\n', "\\n")
                        .replace('\t', "\\t")
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
    // Delimiter and special chars
    if s.contains('\t') || s.contains('\n') || s.contains('\\') || s.contains('"') {
        return true;
    }
    // Tree drawing chars at start
    if s.starts_with('├')
        || s.starts_with('└')
        || s.starts_with('|')
        || s.starts_with('@')
        || s.starts_with('#')
        || s.starts_with('-')
    {
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
                .replace("\\t", "\t")
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
    if let Ok(i) = s.parse::<i64>() {
        return Value::Number(i.into());
    }
    if let Ok(f) = s.parse::<f64>()
        && let Some(n) = serde_json::Number::from_f64(f)
    {
        return Value::Number(n);
    }

    Value::String(s.to_string())
}

/// Parse a columnar cell value
/// Returns None for empty/missing cells, Some(value) for present values (including explicit null)
fn parse_columnar_cell(s: &str) -> Option<Value> {
    let trimmed = s.trim();
    if trimmed.is_empty() {
        // Empty cell means field is missing (absent from object)
        return None;
    }
    // Non-empty cell means field is present (could be explicit "null")
    Some(parse_primitive(s))
}

fn is_uniform_array(arr: &[Value]) -> (bool, Vec<String>) {
    if arr.is_empty() {
        return (false, vec![]);
    }

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
            let encoded = format_primitive(val);
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
            lines.push(format!("{}{}[0]", indent, n));
        } else {
            lines.push(format!("{}[0]", indent));
        }
        return;
    }

    // Check for uniform objects (columnar format)
    let (is_uniform, fields) = is_uniform_array(arr);
    if is_uniform && !fields.is_empty() {
        // Columnar header
        if let Some(n) = name {
            lines.push(format!("{}{}[{}]", indent, n, arr.len()));
        } else {
            lines.push(format!("{}[{}]", indent, arr.len()));
        }

        // Output each field as a column
        let total_fields = fields.len();
        for (i, field) in fields.iter().enumerate() {
            let values: Vec<String> = arr
                .iter()
                .map(|obj| {
                    obj.as_object()
                        .and_then(|m| m.get(field))
                        .map(format_primitive)
                        .unwrap_or_default()
                })
                .collect();

            let prefix = if i == total_fields - 1 { "└" } else { "├" };
            lines.push(format!(
                "{}{} {}: {}",
                indent,
                prefix,
                field,
                values.join(delimiter)
            ));
        }
        return;
    }

    // Primitive array (inline)
    if arr.iter().all(|v| !v.is_object() && !v.is_array()) {
        let values: Vec<String> = arr.iter().map(format_primitive).collect();
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

    // Mixed/nested - use list item format
    if let Some(n) = name {
        lines.push(format!("{}{}[{}]:", indent, n, arr.len()));
    } else {
        lines.push(format!("{}[{}]:", indent, arr.len()));
    }
    for item in arr {
        match item {
            Value::Object(obj) => {
                encode_list_item_object(obj, lines, depth + 1, delimiter);
            }
            _ => {
                lines.push(format!("{}  - {}", indent, format_primitive(item)));
            }
        }
    }
}

/// Encode an object as a list item (- key: value format)
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
                    match nv {
                        Value::Object(_) | Value::Array(_) => {
                            encode_value(nv, lines, depth + 2, delimiter, Some(nk));
                        }
                        _ => {
                            lines.push(format!("{}    {}: {}", indent, nk, format_primitive(nv)));
                        }
                    }
                }
            }
            Value::Array(arr) => {
                lines.push(format!("{}{}:", prefix, k));
                encode_array(arr, lines, depth + 2, delimiter, None);
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
                lines.push(format!("{}{}: {}", actual_indent, k, format_primitive(v)));
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

fn decode_value(
    lines: &[&str],
    idx: usize,
    _depth: usize,
    delimiter: &str,
) -> Result<(Value, usize)> {
    if idx >= lines.len() {
        return Ok((Value::Null, idx));
    }

    let line = lines[idx].trim();
    let base_depth = get_indent_depth(lines[idx]);

    // Check for array patterns: [N], [N]:, name[N], name[N]:
    if let Some(bracket_pos) = line.find('[')
        && let Some(end_pos) = line.find(']')
        && end_pos > bracket_pos
    {
        let name = &line[..bracket_pos];
        let count_str = &line[bracket_pos + 1..end_pos];
        if let Ok(count) = count_str.parse::<usize>() {
            // If this is a named array (name[N]), it's part of an object
            // Delegate to decode_object to parse the full object
            if !name.is_empty() {
                return decode_object(lines, idx, delimiter);
            }

            // Unnamed array: [N]
            // Check if next line has ├ or └ (columnar format)
            if idx + 1 < lines.len() {
                let next = lines[idx + 1].trim();
                if next.starts_with('├') || next.starts_with('└') {
                    return decode_columnar_array(lines, idx, "", count, delimiter);
                }
            }

            // Check for inline primitive array: [N]: val1\tval2
            if let Some(colon_pos) = line.find("]:") {
                let values_str = line[colon_pos + 2..].trim();
                if !values_str.is_empty() {
                    let values: Vec<Value> =
                        values_str.split(delimiter).map(parse_primitive).collect();
                    return Ok((Value::Array(values), idx + 1));
                }
                // Empty values after colon means list array: [N]:
                return decode_list_array(lines, idx, base_depth, count, delimiter);
            }

            // Bare [N] with no colon - could be empty array or non-columnar array
            if count == 0 {
                return Ok((Value::Array(vec![]), idx + 1));
            }
            // Check if next line is a list item
            if idx + 1 < lines.len() {
                let next = lines[idx + 1].trim();
                if next.starts_with("- ") {
                    return decode_list_array(lines, idx, base_depth, count, delimiter);
                }
            }
            // No colon, no columnar, no list - it's an empty array
            return Ok((Value::Array(vec![]), idx + 1));
        }
    }

    // Check for key: value
    if line.contains(':') {
        return decode_object(lines, idx, delimiter);
    }

    Ok((Value::Null, idx + 1))
}

fn decode_columnar_array(
    lines: &[&str],
    idx: usize,
    name: &str,
    count: usize,
    delimiter: &str,
) -> Result<(Value, usize)> {
    let mut fields: Vec<String> = Vec::new();
    // Each column stores Option<Value>: None = missing, Some(v) = present (including explicit null)
    let mut columns: Vec<Vec<Option<Value>>> = Vec::new();

    let mut idx = idx + 1;

    // Parse columnar lines (├ field: val1\tval2... or └ field: val1\tval2...)
    while idx < lines.len() {
        let line = lines[idx].trim();

        let field_line = if let Some(rest) = line.strip_prefix('├') {
            Some(rest.trim())
        } else {
            line.strip_prefix('└').map(|rest| rest.trim())
        };

        if let Some(content) = field_line {
            if let Some(colon_pos) = content.find(':') {
                let field = content[..colon_pos].trim();
                // Don't strip trailing whitespace - it's part of delimiter for empty cells
                let values_str = content[colon_pos + 1..].trim_start();

                fields.push(field.to_string());

                let values: Vec<Option<Value>> = if values_str.is_empty() {
                    vec![]
                } else {
                    split_column_values(values_str, delimiter)
                        .iter()
                        .map(|s| parse_columnar_cell(s))
                        .collect()
                };
                columns.push(values);
            }
            idx += 1;

            if line.starts_with('└') {
                break;
            }
        } else {
            break;
        }
    }

    // Transpose columns to rows, preserving field order
    let mut result: Vec<Value> = Vec::with_capacity(count);
    for i in 0..count {
        let mut obj = Map::new();
        for (j, field) in fields.iter().enumerate() {
            if let Some(col) = columns.get(j) {
                // Only insert if value is present (Some(Some(val))), skip if missing
                if let Some(Some(val)) = col.get(i) {
                    obj.insert(field.clone(), val.clone());
                }
            }
        }
        result.push(Value::Object(obj));
    }

    let arr = Value::Array(result);
    if name.is_empty() {
        Ok((arr, idx))
    } else {
        let mut wrapper = Map::new();
        wrapper.insert(name.to_string(), arr);
        Ok((Value::Object(wrapper), idx))
    }
}

/// Split column values respecting quotes
fn split_column_values(values_str: &str, delimiter: &str) -> Vec<String> {
    let mut result = Vec::new();
    let mut current = String::new();
    let mut in_quote = false;
    let mut chars = values_str.chars().peekable();
    let delim_chars: Vec<char> = delimiter.chars().collect();

    while let Some(c) = chars.next() {
        // Check for delimiter (only when not in quotes)
        if !in_quote && c == delim_chars[0] {
            let mut is_delim = delim_chars.len() == 1;
            if delim_chars.len() > 1 {
                // Check rest of delimiter
                let mut temp = String::new();
                temp.push(c);
                let mut matched = true;
                for (_i, &dc) in delim_chars.iter().enumerate().skip(1) {
                    if let Some(&nc) = chars.peek() {
                        if nc == dc {
                            temp.push(chars.next().unwrap());
                        } else {
                            matched = false;
                            current.push_str(&temp);
                            break;
                        }
                    } else {
                        matched = false;
                        current.push_str(&temp);
                        break;
                    }
                }
                is_delim = matched;
            }
            if is_delim {
                result.push(current);
                current = String::new();
                continue;
            }
        }

        if c == '"' && !in_quote {
            in_quote = true;
            current.push(c);
        } else if c == '"' && in_quote {
            in_quote = false;
            current.push(c);
        } else {
            current.push(c);
        }
    }

    result.push(current);
    result
}

fn decode_object(lines: &[&str], idx: usize, delimiter: &str) -> Result<(Value, usize)> {
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

        // Check for array patterns: name[N] or name[N]: values
        if let Some(bracket_pos) = stripped.find('[')
            && let Some(end_pos) = stripped.find(']')
            && end_pos > bracket_pos
        {
            let name = &stripped[..bracket_pos];
            let count_str = &stripped[bracket_pos + 1..end_pos];
            if let Ok(count) = count_str.parse::<usize>() {
                // This is an array pattern - decode it via decode_value
                let (arr, new_idx) = decode_array_in_object(lines, idx, name, count, delimiter)?;
                result.insert(name.to_string(), arr);
                idx = new_idx;
                continue;
            }
        }

        // Regular key: value parsing
        if let Some(colon_pos) = stripped.find(':') {
            let key = stripped[..colon_pos].trim();
            let val_str = stripped[colon_pos + 1..].trim();

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
                    // End of file - still insert empty object
                    result.insert(key.to_string(), Value::Object(Map::new()));
                }
            }
        } else {
            break;
        }
    }

    Ok((Value::Object(result), idx))
}

/// Decode an array that appears within an object context
fn decode_array_in_object(
    lines: &[&str],
    idx: usize,
    _name: &str,
    count: usize,
    delimiter: &str,
) -> Result<(Value, usize)> {
    let line = lines[idx].trim();
    let base_depth = get_indent_depth(lines[idx]);

    // Check for inline primitive array: name[N]: val1\tval2
    if let Some(colon_pos) = line.find("]:") {
        let values_str = line[colon_pos + 2..].trim();
        if !values_str.is_empty() {
            let values: Vec<Value> = values_str.split(delimiter).map(parse_primitive).collect();
            return Ok((Value::Array(values), idx + 1));
        }
    }

    // Check for columnar array: name[N] followed by ├/└ lines
    if idx + 1 < lines.len() {
        let next = lines[idx + 1].trim();
        if next.starts_with('├') || next.starts_with('└') {
            let (arr, new_idx) = decode_columnar_array(lines, idx, "", count, delimiter)?;
            return Ok((arr, new_idx));
        }
    }

    // Check for list array: name[N]: followed by - items
    if line.ends_with(':') {
        return decode_list_array(lines, idx, base_depth, count, delimiter);
    }

    // Empty array
    Ok((Value::Array(vec![]), idx + 1))
}

/// Decode a list array: name[N]: followed by - items
fn decode_list_array(
    lines: &[&str],
    idx: usize,
    base_depth: usize,
    count: usize,
    delimiter: &str,
) -> Result<(Value, usize)> {
    let mut result: Vec<Value> = Vec::new();
    let mut idx = idx + 1;
    let item_depth = base_depth + 1;

    while idx < lines.len() && result.len() < count {
        let line = lines[idx];
        if line.trim().is_empty() {
            idx += 1;
            continue;
        }

        let line_depth = get_indent_depth(line);
        if line_depth < item_depth {
            break;
        }

        let stripped = line.trim();
        if let Some(item_str) = stripped.strip_prefix("- ") {
            // Check if it's key: value (object) or primitive
            if item_str.contains(':') {
                let (obj, new_idx) = decode_list_item_object(lines, idx, item_depth, delimiter)?;
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

/// Decode an object that starts with '- key: value'
fn decode_list_item_object(
    lines: &[&str],
    idx: usize,
    item_depth: usize,
    delimiter: &str,
) -> Result<(Value, usize)> {
    let mut obj = Map::new();

    let first_line = lines[idx].trim();
    let first_content = first_line.strip_prefix("- ").unwrap_or(first_line).trim();

    let mut idx = idx;

    // Parse first key: value
    if let Some(colon_pos) = first_content.find(':') {
        let key = first_content[..colon_pos].trim();
        let val_str = first_content[colon_pos + 1..].trim();

        if !val_str.is_empty() {
            obj.insert(key.to_string(), parse_primitive(val_str));
            idx += 1;
        } else {
            // Nested value or empty object
            idx += 1;
            if idx < lines.len() {
                let next_depth = get_indent_depth(lines[idx]);
                if next_depth > item_depth {
                    let (nested, new_idx) = decode_value(lines, idx, next_depth, delimiter)?;
                    obj.insert(key.to_string(), nested);
                    idx = new_idx;
                } else {
                    obj.insert(key.to_string(), Value::Object(Map::new()));
                }
            } else {
                // No more lines - empty object
                obj.insert(key.to_string(), Value::Object(Map::new()));
            }
        }
    } else {
        idx += 1;
    }

    // Parse continuation lines (indented under the list item)
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

        // New list item at same level means end of this object
        if stripped.starts_with("- ") {
            break;
        }

        // Check for array patterns
        if let Some(bracket_pos) = stripped.find('[')
            && let Some(end_pos) = stripped.find(']')
            && end_pos > bracket_pos
        {
            let arr_name = &stripped[..bracket_pos];
            let count_str = &stripped[bracket_pos + 1..end_pos];
            if let Ok(count) = count_str.parse::<usize>() {
                let (arr, new_idx) =
                    decode_array_in_object(lines, idx, arr_name, count, delimiter)?;
                obj.insert(arr_name.to_string(), arr);
                idx = new_idx;
                continue;
            }
        }

        // Regular key: value
        if let Some(colon_pos) = stripped.find(':') {
            let key = stripped[..colon_pos].trim();
            let val_str = stripped[colon_pos + 1..].trim();

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

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // ========================================================================
    // Encoding tests
    // ========================================================================

    #[test]
    fn test_encode_columnar() {
        let data = json!([
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ]);
        let encoded = encode(&data, false).unwrap();
        assert!(encoded.contains("[2]"));
        assert!(encoded.contains("├") || encoded.contains("└"));
    }

    #[test]
    fn test_encode_with_header() {
        let data = json!({"name": "test"});
        let encoded = encode(&data, true).unwrap();
        assert!(encoded.starts_with("@AGON columns"));
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
        assert!(encoded.contains("bool_true: true"));
        assert!(encoded.contains("null_val: null"));
    }

    #[test]
    fn test_encode_empty_array() {
        let data = json!({"items": []});
        let encoded = encode(&data, false).unwrap();
        assert!(encoded.contains("items[0]"));
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

    #[test]
    fn test_encode_columnar_tree_chars() {
        let data = json!([
            {"a": 1, "b": 2, "c": 3}
        ]);
        let encoded = encode(&data, false).unwrap();
        // Should have ├ for non-last and └ for last
        assert!(encoded.contains("├") || encoded.contains("└"));
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
        let result = decode("@AGON columns\n\n").unwrap();
        assert!(result.is_null());
    }

    #[test]
    fn test_decode_simple_object() {
        let payload = "@AGON columns\n\nname: Alice\nage: 30";
        let decoded = decode(payload).unwrap();
        assert_eq!(decoded["name"], "Alice");
        assert_eq!(decoded["age"], 30);
    }

    #[test]
    fn test_decode_columnar_array() {
        let payload = "@AGON columns\n\n[2]\n├ id: 1\t2\n└ name: Alice\tBob";
        let decoded = decode(payload).unwrap();
        assert!(decoded.is_array());
        let arr = decoded.as_array().unwrap();
        assert_eq!(arr.len(), 2);
        assert_eq!(arr[0]["id"], 1);
        assert_eq!(arr[0]["name"], "Alice");
        assert_eq!(arr[1]["id"], 2);
        assert_eq!(arr[1]["name"], "Bob");
    }

    #[test]
    fn test_decode_named_columnar_array() {
        let payload = "@AGON columns\n\nusers[2]\n├ id: 1\t2\n└ name: Alice\tBob";
        let decoded = decode(payload).unwrap();
        assert!(decoded.is_object());
        let users = decoded["users"].as_array().unwrap();
        assert_eq!(users.len(), 2);
    }

    #[test]
    fn test_decode_primitive_array() {
        let payload = "@AGON columns\n\nnums[3]: 1\t2\t3";
        let decoded = decode(payload).unwrap();
        let nums = decoded["nums"].as_array().unwrap();
        assert_eq!(nums.len(), 3);
        assert_eq!(nums[0], 1);
    }

    #[test]
    fn test_decode_empty_array() {
        let payload = "@AGON columns\n\nitems[0]";
        let decoded = decode(payload).unwrap();
        let items = decoded["items"].as_array().unwrap();
        assert!(items.is_empty());
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
    fn test_roundtrip_nested() {
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
        assert!(needs_quote(""));
    }

    #[test]
    fn test_needs_quote_whitespace() {
        assert!(needs_quote("  padded  "));
        assert!(needs_quote(" leading"));
    }

    #[test]
    fn test_needs_quote_delimiter() {
        assert!(needs_quote("has\ttab"));
        assert!(needs_quote("has\nnewline"));
    }

    #[test]
    fn test_needs_quote_special_chars() {
        assert!(needs_quote("has\"quote"));
        assert!(needs_quote("has\\backslash"));
    }

    #[test]
    fn test_needs_quote_tree_chars() {
        assert!(needs_quote("├ branch"));
        assert!(needs_quote("└ leaf"));
        assert!(needs_quote("| pipe"));
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
    fn test_parse_primitive_null() {
        assert_eq!(parse_primitive("null"), Value::Null);
        assert_eq!(parse_primitive("NULL"), Value::Null);
        assert_eq!(parse_primitive(""), Value::Null);
    }

    #[test]
    fn test_parse_primitive_bool() {
        assert_eq!(parse_primitive("true"), Value::Bool(true));
        assert_eq!(parse_primitive("false"), Value::Bool(false));
    }

    #[test]
    fn test_parse_primitive_number() {
        assert_eq!(parse_primitive("42"), json!(42));
        assert_eq!(parse_primitive("-17"), json!(-17));
        assert_eq!(parse_primitive("3.15"), json!(3.15));
    }

    #[test]
    fn test_parse_primitive_quoted_string() {
        assert_eq!(
            parse_primitive("\"hello\""),
            Value::String("hello".to_string())
        );
        assert_eq!(
            parse_primitive("\"line\\nbreak\""),
            Value::String("line\nbreak".to_string())
        );
    }

    #[test]
    fn test_parse_columnar_cell_empty() {
        assert_eq!(parse_columnar_cell(""), None);
        assert_eq!(parse_columnar_cell("  "), None);
    }

    #[test]
    fn test_parse_columnar_cell_value() {
        assert_eq!(parse_columnar_cell("42"), Some(json!(42)));
        assert_eq!(parse_columnar_cell("null"), Some(Value::Null));
    }

    #[test]
    fn test_is_uniform_array_empty() {
        let arr: Vec<Value> = vec![];
        let (uniform, _) = is_uniform_array(&arr);
        assert!(!uniform);
    }

    #[test]
    fn test_is_uniform_array_primitives() {
        let arr = vec![json!(1), json!(2)];
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
    fn test_is_uniform_array_nested() {
        let arr = vec![json!({"nested": {"a": 1}})];
        let (uniform, _) = is_uniform_array(&arr);
        assert!(!uniform); // Contains nested object
    }

    #[test]
    fn test_split_column_values_simple() {
        let values = split_column_values("a\tb\tc", "\t");
        assert_eq!(values, vec!["a", "b", "c"]);
    }

    #[test]
    fn test_split_column_values_quoted() {
        let values = split_column_values("\"a\tb\"\tc", "\t");
        assert_eq!(values, vec!["\"a\tb\"", "c"]);
    }

    #[test]
    fn test_split_column_values_empty() {
        let values = split_column_values("a\t\tc", "\t");
        assert_eq!(values, vec!["a", "", "c"]);
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
    fn test_unicode_strings() {
        let data = json!({"text": "Hello 世界"});
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert_eq!(decoded["text"], "Hello 世界");
    }

    #[test]
    fn test_long_string() {
        let long = "x".repeat(500);
        let data = json!({"text": long});
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert_eq!(decoded["text"].as_str().unwrap().len(), 500);
    }

    #[test]
    fn test_many_columns() {
        let data = json!([
            {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}
        ]);
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert!(decoded.is_array());
    }

    #[test]
    fn test_missing_values_in_column() {
        // Some objects have fewer fields
        let data = json!([
            {"id": 1, "name": "Alice", "email": "a@b.com"},
            {"id": 2, "name": "Bob"}  // No email
        ]);
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        let arr = decoded.as_array().unwrap();
        assert_eq!(arr[0]["email"], "a@b.com");
        // Bob should not have email key at all (not null, just missing)
        assert!(arr[1].get("email").is_none() || arr[1]["email"].is_null());
    }

    #[test]
    fn test_list_array_with_objects() {
        let data = json!({
            "items": [
                {"type": "a", "nested": {"x": 1}},
                {"type": "b", "nested": {"x": 2}}
            ]
        });
        let encoded = encode(&data, true).unwrap();
        let decoded = decode(&encoded).unwrap();
        assert!(decoded["items"].is_array());
    }
}
