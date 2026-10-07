## Implementation taken from Rust Standard Library (https://doc.rust-lang.org/stable/src/core/num/int_macros.rs.html#3424)
def next_multiple_of(lhs: int, rhs: int) -> int:
    if rhs == -1:
        return lhs

    r: int = lhs % rhs
    m: int = r + rhs if ((r > 0 and rhs < 0) or (r < 0 and rhs > 0)) else r

    return lhs if m == 0 else lhs + (rhs - m)


def read_binary_file(path: str, encoding: str = "utf-8") -> bytes:
    with open(path, "rb", encoding=encoding) as f:
        return f.read()


def read_text_file(path: str, encoding: str = "utf-8") -> str:
    with open(path, "r", encoding=encoding) as f:
        return f.read()


def unwrap[T](value: T | None) -> T:
    if value is None:
        raise ValueError("Value was null")
    return value


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'
