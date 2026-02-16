use std::collections::BTreeMap;
use std::fmt;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum GcjValue {
    Null,
    Bool(bool),
    Int(i64),
    Str(String),
    Array(Vec<GcjValue>),
    Object(BTreeMap<String, GcjValue>),
}

#[derive(Debug)]
pub enum GcjError {
    Parse(String),
}

impl fmt::Display for GcjError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            GcjError::Parse(msg) => write!(f, "{msg}"),
        }
    }
}

pub fn parse_gcj(bytes: &[u8]) -> Result<GcjValue, GcjError> {
    let mut parser = Parser::new(bytes);
    let value = parser.parse_value()?;
    parser.skip_ws();
    if parser.idx != parser.bytes.len() {
        return Err(GcjError::Parse("trailing data".to_string()));
    }
    Ok(value)
}

pub fn canonical_bytes(value: &GcjValue) -> Vec<u8> {
    let mut out = String::new();
    write_canonical(value, &mut out);
    out.into_bytes()
}

pub fn canonicalize_bytes(raw: &[u8]) -> Result<Vec<u8>, GcjError> {
    let value = parse_gcj(raw)?;
    Ok(canonical_bytes(&value))
}

fn write_canonical(value: &GcjValue, out: &mut String) {
    match value {
        GcjValue::Null => out.push_str("null"),
        GcjValue::Bool(true) => out.push_str("true"),
        GcjValue::Bool(false) => out.push_str("false"),
        GcjValue::Int(i) => out.push_str(&i.to_string()),
        GcjValue::Str(s) => write_string(s, out),
        GcjValue::Array(items) => {
            out.push('[');
            for (idx, item) in items.iter().enumerate() {
                if idx > 0 {
                    out.push(',');
                }
                write_canonical(item, out);
            }
            out.push(']');
        }
        GcjValue::Object(map) => {
            out.push('{');
            for (idx, (k, v)) in map.iter().enumerate() {
                if idx > 0 {
                    out.push(',');
                }
                write_string(k, out);
                out.push(':');
                write_canonical(v, out);
            }
            out.push('}');
        }
    }
}

fn write_string(value: &str, out: &mut String) {
    out.push('"');
    for c in value.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0C}' => out.push_str("\\f"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => {
                out.push_str(&format!("\\u{:04x}", c as u32));
            }
            _ => out.push(c),
        }
    }
    out.push('"');
}

struct Parser<'a> {
    bytes: &'a [u8],
    idx: usize,
}

impl<'a> Parser<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, idx: 0 }
    }

    fn parse_value(&mut self) -> Result<GcjValue, GcjError> {
        self.skip_ws();
        match self.peek() {
            Some(b'n') => self.parse_null(),
            Some(b't') | Some(b'f') => self.parse_bool(),
            Some(b'"') => self.parse_string().map(GcjValue::Str),
            Some(b'{') => self.parse_object(),
            Some(b'[') => self.parse_array(),
            Some(b'-') | Some(b'0'..=b'9') => self.parse_number(),
            Some(other) => Err(GcjError::Parse(format!("unexpected byte: {other}"))),
            None => Err(GcjError::Parse("unexpected end of input".to_string())),
        }
    }

    fn parse_null(&mut self) -> Result<GcjValue, GcjError> {
        if self.consume_literal(b"null") {
            Ok(GcjValue::Null)
        } else {
            Err(GcjError::Parse("invalid literal".to_string()))
        }
    }

    fn parse_bool(&mut self) -> Result<GcjValue, GcjError> {
        if self.consume_literal(b"true") {
            Ok(GcjValue::Bool(true))
        } else if self.consume_literal(b"false") {
            Ok(GcjValue::Bool(false))
        } else {
            Err(GcjError::Parse("invalid literal".to_string()))
        }
    }

    fn parse_string(&mut self) -> Result<String, GcjError> {
        self.expect_byte(b'"')?;
        let mut buf = Vec::new();
        loop {
            let b = self.next_byte().ok_or_else(|| GcjError::Parse("unterminated string".to_string()))?;
            match b {
                b'"' => break,
                b'\\' => {
                    let esc = self.next_byte().ok_or_else(|| GcjError::Parse("unterminated escape".to_string()))?;
                    match esc {
                        b'"' => buf.push(b'"'),
                        b'\\' => buf.push(b'\\'),
                        b'/' => buf.push(b'/'),
                        b'b' => buf.push(0x08),
                        b'f' => buf.push(0x0C),
                        b'n' => buf.push(b'\n'),
                        b'r' => buf.push(b'\r'),
                        b't' => buf.push(b'\t'),
                        b'u' => {
                            let cp = self.parse_hex4()?;
                            if (0xD800..=0xDBFF).contains(&cp) {
                                self.expect_byte(b'\\')?;
                                self.expect_byte(b'u')?;
                                let low = self.parse_hex4()?;
                                if !(0xDC00..=0xDFFF).contains(&low) {
                                    return Err(GcjError::Parse("invalid surrogate pair".to_string()));
                                }
                                let high_ten = (cp as u32 - 0xD800) << 10;
                                let low_ten = low as u32 - 0xDC00;
                                let scalar = 0x10000 + (high_ten | low_ten);
                                let ch = char::from_u32(scalar).ok_or_else(|| GcjError::Parse("invalid codepoint".to_string()))?;
                                let mut tmp = [0u8; 4];
                                buf.extend_from_slice(ch.encode_utf8(&mut tmp).as_bytes());
                            } else if (0xDC00..=0xDFFF).contains(&cp) {
                                return Err(GcjError::Parse("invalid surrogate".to_string()));
                            } else {
                                let ch = char::from_u32(cp as u32).ok_or_else(|| GcjError::Parse("invalid codepoint".to_string()))?;
                                let mut tmp = [0u8; 4];
                                buf.extend_from_slice(ch.encode_utf8(&mut tmp).as_bytes());
                            }
                        }
                        _ => return Err(GcjError::Parse("invalid escape".to_string())),
                    }
                }
                0x00..=0x1F => return Err(GcjError::Parse("control character in string".to_string())),
                _ => buf.push(b),
            }
        }
        String::from_utf8(buf).map_err(|_| GcjError::Parse("invalid utf-8".to_string()))
    }

    fn parse_array(&mut self) -> Result<GcjValue, GcjError> {
        self.expect_byte(b'[')?;
        let mut items = Vec::new();
        self.skip_ws();
        if self.peek() == Some(b']') {
            self.idx += 1;
            return Ok(GcjValue::Array(items));
        }
        loop {
            let value = self.parse_value()?;
            items.push(value);
            self.skip_ws();
            match self.next_byte() {
                Some(b',') => continue,
                Some(b']') => break,
                _ => return Err(GcjError::Parse("expected ',' or ']'".to_string())),
            }
        }
        Ok(GcjValue::Array(items))
    }

    fn parse_object(&mut self) -> Result<GcjValue, GcjError> {
        self.expect_byte(b'{')?;
        let mut map = BTreeMap::new();
        self.skip_ws();
        if self.peek() == Some(b'}') {
            self.idx += 1;
            return Ok(GcjValue::Object(map));
        }
        loop {
            self.skip_ws();
            let key = self.parse_string()?;
            if map.contains_key(&key) {
                return Err(GcjError::Parse("duplicate object key".to_string()));
            }
            self.skip_ws();
            self.expect_byte(b':')?;
            let value = self.parse_value()?;
            map.insert(key, value);
            self.skip_ws();
            match self.next_byte() {
                Some(b',') => continue,
                Some(b'}') => break,
                _ => return Err(GcjError::Parse("expected ',' or '}'".to_string())),
            }
        }
        Ok(GcjValue::Object(map))
    }

    fn parse_number(&mut self) -> Result<GcjValue, GcjError> {
        let start = self.idx;
        let mut negative = false;
        if self.peek() == Some(b'-') {
            negative = true;
            self.idx += 1;
        }
        let first = self.peek().ok_or_else(|| GcjError::Parse("invalid number".to_string()))?;
        if !matches!(first, b'0'..=b'9') {
            return Err(GcjError::Parse("invalid number".to_string()));
        }
        if first == b'0' {
            self.idx += 1;
            if matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(GcjError::Parse("leading zero".to_string()));
            }
        } else {
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.idx += 1;
            }
        }
        let end = self.idx;
        if matches!(self.peek(), Some(b'.') | Some(b'e') | Some(b'E') | Some(b'+')) {
            return Err(GcjError::Parse("non-integer number".to_string()));
        }
        let s = std::str::from_utf8(&self.bytes[start..end])
            .map_err(|_| GcjError::Parse("invalid number".to_string()))?;
        let mut value: i128 = 0;
        for b in s.as_bytes() {
            if *b == b'-' {
                continue;
            }
            value = value * 10 + (b - b'0') as i128;
            if value > i64::MAX as i128 + 1 {
                return Err(GcjError::Parse("integer overflow".to_string()));
            }
        }
        if negative {
            value = -value;
        }
        if value < i64::MIN as i128 || value > i64::MAX as i128 {
            return Err(GcjError::Parse("integer overflow".to_string()));
        }
        Ok(GcjValue::Int(value as i64))
    }

    fn parse_hex4(&mut self) -> Result<u16, GcjError> {
        let mut val: u16 = 0;
        for _ in 0..4 {
            let b = self.next_byte().ok_or_else(|| GcjError::Parse("unterminated unicode escape".to_string()))?;
            val = (val << 4) | match b {
                b'0'..=b'9' => (b - b'0') as u16,
                b'a'..=b'f' => (10 + (b - b'a')) as u16,
                b'A'..=b'F' => (10 + (b - b'A')) as u16,
                _ => return Err(GcjError::Parse("invalid unicode escape".to_string())),
            };
        }
        Ok(val)
    }

    fn consume_literal(&mut self, literal: &[u8]) -> bool {
        if self.bytes.len() >= self.idx + literal.len()
            && &self.bytes[self.idx..self.idx + literal.len()] == literal
        {
            self.idx += literal.len();
            true
        } else {
            false
        }
    }

    fn skip_ws(&mut self) {
        while let Some(b) = self.peek() {
            if matches!(b, b' ' | b'\n' | b'\r' | b'\t') {
                self.idx += 1;
            } else {
                break;
            }
        }
    }

    fn expect_byte(&mut self, expected: u8) -> Result<(), GcjError> {
        match self.next_byte() {
            Some(b) if b == expected => Ok(()),
            _ => Err(GcjError::Parse("unexpected byte".to_string())),
        }
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.idx).copied()
    }

    fn next_byte(&mut self) -> Option<u8> {
        let b = self.bytes.get(self.idx).copied();
        if b.is_some() {
            self.idx += 1;
        }
        b
    }
}
