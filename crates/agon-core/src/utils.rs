//! Shared utilities for AGON encoding

use std::collections::HashMap;
use std::sync::{LazyLock, RwLock};
use tiktoken_rs::CoreBPE;

use crate::error::{AgonError, Result};

/// Cached tokenizer instances by encoding name
static TOKENIZERS: LazyLock<RwLock<HashMap<String, CoreBPE>>> =
    LazyLock::new(|| RwLock::new(HashMap::new()));

/// Get or create a tokenizer for the given encoding
fn get_tokenizer(encoding: &str) -> Result<CoreBPE> {
    // Check cache first
    {
        let cache = TOKENIZERS.read().unwrap();
        if let Some(tokenizer) = cache.get(encoding) {
            return Ok(tokenizer.clone());
        }
    }

    // Create new tokenizer
    let tokenizer = match encoding {
        "o200k_base" => tiktoken_rs::o200k_base(),
        "o200k_harmony" => tiktoken_rs::o200k_harmony(),
        "cl100k_base" => tiktoken_rs::cl100k_base(),
        "p50k_base" => tiktoken_rs::p50k_base(),
        "p50k_edit" => tiktoken_rs::p50k_edit(),
        "r50k_base" => tiktoken_rs::r50k_base(),
        _ => {
            return Err(AgonError::InvalidFormat(format!(
                "Unknown encoding: {}",
                encoding
            )));
        }
    }
    .map_err(|e| AgonError::EncodingError(e.to_string()))?;

    // Cache it
    {
        let mut cache = TOKENIZERS.write().unwrap();
        cache.insert(encoding.to_string(), tokenizer.clone());
    }

    Ok(tokenizer)
}

/// Count tokens using the specified tiktoken encoding
/// Note: This is expensive (~1ms per 10KB). Use only when exact count is needed.
pub fn count_tokens(text: &str, encoding: &str) -> Result<usize> {
    let tokenizer = get_tokenizer(encoding)?;
    Ok(tokenizer.encode_ordinary(text).len())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_count_tokens() {
        assert!(count_tokens("hello world", "o200k_base").unwrap() > 0);
        assert!(
            count_tokens("a longer piece of text", "o200k_base").unwrap()
                > count_tokens("short", "o200k_base").unwrap()
        );
        assert_eq!(count_tokens("", "o200k_base").unwrap(), 0);
    }

    #[test]
    fn test_count_tokens_invalid_encoding() {
        assert!(count_tokens("hello", "invalid_encoding").is_err());
    }
}
