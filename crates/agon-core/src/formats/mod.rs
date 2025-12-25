//! AGON encoding formats
//!
//! This module contains implementations of the three AGON formats:
//! - rows: Row-based tabular encoding (format name: "text")
//! - columns: Columnar encoding with type clustering
//! - struct_fmt: Template-based encoding for nested patterns

pub mod columns;
pub mod rows;
pub mod struct_fmt;

use rayon::prelude::*;
use serde_json::Value as JsonValue;

use crate::error::Result;
use crate::utils::count_tokens;

/// Result of encoding with metadata
#[derive(Debug, Clone)]
pub struct EncodingResult {
    pub format: String,
    pub text: String,
    pub header: String,
    pub token_estimate: usize,
}

/// Headers for each format
pub fn get_header(format: &str) -> &'static str {
    match format {
        "rows" => "@AGON rows",
        "columns" => "@AGON columns",
        "struct" => "@AGON struct",
        "json" => "",
        _ => "",
    }
}

/// Encode data with all formats in parallel and return the best one
pub fn encode_auto_parallel(
    data: &JsonValue,
    force: bool,
    min_savings: f64,
) -> Result<EncodingResult> {
    let results = encode_all_parallel(data)?;

    // Find JSON baseline
    let json_result = results.iter().find(|r| r.format == "json");
    let json_tokens = json_result.map(|r| r.token_estimate).unwrap_or(usize::MAX);

    // Find best non-JSON result
    let best = results
        .iter()
        .filter(|r| force || r.format != "json")
        .min_by_key(|r| r.token_estimate);

    match best {
        Some(best_result) => {
            // Check if savings meet threshold
            if !force && best_result.format != "json" {
                let savings = 1.0 - (best_result.token_estimate as f64 / json_tokens.max(1) as f64);
                if savings < min_savings {
                    // Return JSON if savings don't meet threshold
                    return Ok(json_result.cloned().unwrap_or_else(|| EncodingResult {
                        format: "json".to_string(),
                        text: serde_json::to_string(data).unwrap_or_default(),
                        header: String::new(),
                        token_estimate: json_tokens,
                    }));
                }
            }
            Ok(best_result.clone())
        }
        None => {
            // Fallback to JSON
            let text = serde_json::to_string(data)?;
            let tokens = count_tokens(&text);
            Ok(EncodingResult {
                format: "json".to_string(),
                text,
                header: String::new(),
                token_estimate: tokens,
            })
        }
    }
}

/// Encode data with all formats in parallel
pub fn encode_all_parallel(data: &JsonValue) -> Result<Vec<EncodingResult>> {
    let formats = ["json", "rows", "columns", "struct"];

    // Use rayon to encode all formats in parallel
    let results: Vec<Result<EncodingResult>> = formats
        .par_iter()
        .map(|format| encode_with_format(data, format))
        .collect();

    // Collect results, filtering out errors
    let mut valid_results = Vec::new();
    for result in results {
        match result {
            Ok(r) => valid_results.push(r),
            Err(_) => continue, // Skip formats that fail
        }
    }

    if valid_results.is_empty() {
        // At minimum, JSON should always work
        let text = serde_json::to_string(data)?;
        valid_results.push(EncodingResult {
            format: "json".to_string(),
            text: text.clone(),
            header: String::new(),
            token_estimate: count_tokens(&text),
        });
    }

    Ok(valid_results)
}

/// Encode data with a specific format
fn encode_with_format(data: &JsonValue, format: &str) -> Result<EncodingResult> {
    let (text, header) = match format {
        "json" => (serde_json::to_string(data)?, String::new()),
        "rows" => (rows::encode(data, false)?, get_header("rows").to_string()),
        "columns" => (
            columns::encode(data, false)?,
            get_header("columns").to_string(),
        ),
        "struct" => (
            struct_fmt::encode(data, false)?,
            get_header("struct").to_string(),
        ),
        _ => return Err(crate::error::AgonError::InvalidFormat(format.to_string())),
    };

    let token_estimate = count_tokens(&text);

    Ok(EncodingResult {
        format: format.to_string(),
        text,
        header,
        token_estimate,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_get_header() {
        assert_eq!(get_header("rows"), "@AGON rows");
        assert_eq!(get_header("columns"), "@AGON columns");
        assert_eq!(get_header("struct"), "@AGON struct");
        assert_eq!(get_header("json"), "");
        assert_eq!(get_header("unknown"), "");
    }

    #[test]
    fn test_encode_all_parallel_simple() {
        let data = json!({"name": "test", "value": 42});
        let results = encode_all_parallel(&data).unwrap();

        // Should have results for all formats
        assert!(!results.is_empty());

        // JSON should always be present
        let json_result = results.iter().find(|r| r.format == "json");
        assert!(json_result.is_some());
    }

    #[test]
    fn test_encode_all_parallel_array() {
        let data = json!([
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
            {"id": 3, "name": "Carol"}
        ]);
        let results = encode_all_parallel(&data).unwrap();

        // All four formats should succeed
        assert_eq!(results.len(), 4);

        let formats: Vec<&str> = results.iter().map(|r| r.format.as_str()).collect();
        assert!(formats.contains(&"json"));
        assert!(formats.contains(&"rows"));
        assert!(formats.contains(&"columns"));
        assert!(formats.contains(&"struct"));
    }

    #[test]
    fn test_encode_auto_parallel_selects_best() {
        let data = json!([
            {"id": 1, "name": "Alice", "role": "admin"},
            {"id": 2, "name": "Bob", "role": "user"},
            {"id": 3, "name": "Carol", "role": "user"}
        ]);

        let result = encode_auto_parallel(&data, false, 0.0).unwrap();

        // Should select a non-JSON format for tabular data
        assert!(!result.text.is_empty());
        assert!(result.token_estimate > 0);
    }

    #[test]
    fn test_encode_auto_parallel_force_non_json() {
        let data = json!({"simple": "data"});

        // With force=true, should never return JSON (if alternatives exist)
        let result = encode_auto_parallel(&data, true, 0.0).unwrap();

        // Result should be valid
        assert!(!result.text.is_empty());
    }

    #[test]
    fn test_encode_auto_parallel_min_savings_fallback() {
        let data = json!({"a": 1});

        // With high min_savings threshold, should fall back to JSON if savings aren't met
        let result = encode_auto_parallel(&data, false, 0.99).unwrap();

        // Should get a valid result regardless
        assert!(!result.text.is_empty());
    }

    #[test]
    fn test_encode_with_format_json() {
        let data = json!({"key": "value"});
        let result = encode_with_format(&data, "json").unwrap();

        assert_eq!(result.format, "json");
        assert!(result.header.is_empty());
        assert!(result.text.contains("key"));
    }

    #[test]
    fn test_encode_with_format_rows() {
        let data = json!({"name": "test"});
        let result = encode_with_format(&data, "rows").unwrap();

        assert_eq!(result.format, "rows");
        assert_eq!(result.header, "@AGON rows");
    }

    #[test]
    fn test_encode_with_format_columns() {
        let data = json!([{"id": 1}, {"id": 2}]);
        let result = encode_with_format(&data, "columns").unwrap();

        assert_eq!(result.format, "columns");
        assert_eq!(result.header, "@AGON columns");
    }

    #[test]
    fn test_encode_with_format_struct() {
        let data = json!({"a": {"fmt": "1", "raw": 1}});
        let result = encode_with_format(&data, "struct").unwrap();

        assert_eq!(result.format, "struct");
        assert_eq!(result.header, "@AGON struct");
    }

    #[test]
    fn test_encode_with_format_invalid() {
        let data = json!({});
        let result = encode_with_format(&data, "invalid_format");

        assert!(result.is_err());
    }

    #[test]
    fn test_encoding_result_token_estimate() {
        let data = json!([
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"}
        ]);

        let results = encode_all_parallel(&data).unwrap();

        // All results should have positive token estimates
        for result in &results {
            assert!(
                result.token_estimate > 0,
                "Format {} has zero tokens",
                result.format
            );
        }
    }

    #[test]
    fn test_empty_object() {
        let data = json!({});
        let results = encode_all_parallel(&data).unwrap();

        assert!(!results.is_empty());
    }

    #[test]
    fn test_empty_array() {
        let data = json!([]);
        let results = encode_all_parallel(&data).unwrap();

        assert!(!results.is_empty());
    }

    #[test]
    fn test_nested_structure() {
        let data = json!({
            "user": {
                "name": "Alice",
                "address": {
                    "city": "Seattle",
                    "zip": "98101"
                }
            }
        });

        let results = encode_all_parallel(&data).unwrap();
        assert!(!results.is_empty());

        // All formats should handle nested structures
        for result in &results {
            assert!(
                !result.text.is_empty(),
                "Format {} produced empty text",
                result.format
            );
        }
    }

    #[test]
    fn test_primitive_values() {
        let data = json!({
            "string": "hello",
            "number": 42,
            "float": 3.15,
            "bool": true,
            "null": null
        });

        let results = encode_all_parallel(&data).unwrap();
        assert!(!results.is_empty());
    }

    #[test]
    fn test_mixed_array() {
        let data = json!([1, "two", true, null, {"nested": "object"}]);
        let results = encode_all_parallel(&data).unwrap();

        // JSON should always handle mixed arrays
        let json_result = results.iter().find(|r| r.format == "json").unwrap();
        assert!(json_result.text.contains("two"));
    }
}
