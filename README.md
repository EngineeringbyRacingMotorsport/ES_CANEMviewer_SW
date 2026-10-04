# Storage/Transmission Packet

- Arbitration ID
    - LEB128 Encoded Unsigned Integral
        - Max Value: 0x1FFF_FFFF
- Timestamp
    - LEB128 Encoded Unsigned Integral
        - Max Value: 0xFFFFFFFF
- Length
    - 8 Bit Unsigned Integral
- Data
    - Max length: 8 bytes

Min Packet Size: 1 + 1 + 0 = 2
Max Packet Size: 5 + 1 + 8 = 14
