//! Shared utilities for AGON encoding

use std::sync::OnceLock;
use tiktoken_rs::CoreBPE;

/// Global tokenizer instance (o200k_base - used by GPT-4o/Claude)
static TOKENIZER: OnceLock<CoreBPE> = OnceLock::new();

fn get_tokenizer() -> &'static CoreBPE {
    TOKENIZER.get_or_init(|| {
        tiktoken_rs::o200k_base().expect("Failed to initialize o200k_base tokenizer")
    })
}

/// Count tokens using tiktoken's o200k_base encoding
pub fn count_tokens(text: &str) -> usize {
    get_tokenizer().encode_ordinary(text).len()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_count_tokens() {
        assert!(count_tokens("hello world") > 0);
        assert!(count_tokens("a longer piece of text") > count_tokens("short"));
        assert_eq!(count_tokens(""), 0);
    }
}
