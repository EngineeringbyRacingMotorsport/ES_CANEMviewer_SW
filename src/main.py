from .can import read_file
from .schema import get_connection
from .utils import unwrap

conn = unwrap(get_connection("EMXCAN.json"))
read_file("example.cpf")
with open("example.sqlite", "wb") as f:
    f.write(conn.serialize())
