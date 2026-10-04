from .schema import get_can
from .can import CanReader

reader = CanReader("example.cpf", get_can("EMXCAN.json"))
print(reader.next())
