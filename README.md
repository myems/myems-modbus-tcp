## MyEMS Modbus TCP Service

### Introduction
This service is a component of MyEMS to acquire data from Modbus TCP devices.



### Prerequisites
pyserial

modbus-tk

mysql.connector

### Installation

Download and install MySQL Connector:
```
    $ cd ~/tools
    $ wget https://dev.mysql.com/get/Downloads/Connector-Python/mysql-connector-python-8.0.20.tar.gz
    $ tar xzf mysql-connector-python-8.0.20.tar.gz
    $ cd ~/tools/mysql-connector-python-8.0.20
    $ sudo python3 setup.py install
```

Download and install modbus-tk
```
    $ cd ~/tools
    $ git clone https://github.com/pyserial/pyserial.git
    $ cd ~/tools/pyserial
    $ sudo python3 setup.py install
    $ git clone https://github.com/ljean/modbus-tk.git
    $ cd ~/tools/modbus-tk
    $ sudo python3 setup.py install

```

Install myems-modbus-tcp service
```
    $ cd ~
    $ git clone https://github.com/myems/myesm-modbus-tcp.git
    $ sudo cp -R ~/myems-modbus-tcp /myems-modbus-tcp
    $ cd /myems-modbus-tcp
    $ sudo git checkout master (or the release tag)
```
```
    $ cd ~
    $ git clone https://github.com/myems/myems-modbus-tcp.git
    $ sudo git checkout master (or the release tag)
    $ sudo cp -R ~/myems-modbus-tcp /myems-modbus-tcp
```
    Eidt the config
```
    $ sudo nano /myems-modbus-tcp/config.py
```
    Setup systemd service:
```
    $ sudo cp /myems-modbus-tcp/myems-modbus-tcp.service /lib/systemd/system/
    $ sudo systemctl enable myems-modbus-tcp.service
    $ sudo systemctl start myems-modbus-tcp.service
```



### Add Data Sources and Points in MyEMS Admin 
refer to https://github.com/myems/myesm-admin.git

NOTE: If you modified Modbus TCP datasources and points, please restart this service:
```
    $ sudo systemctl restart myems-modbus-tcp.service
```

Input Data source protocol: 
```
modbus-tcp
```
Data source connection example:
```
{"host":"10.9.67.99","port":502}
```

Point address example:
```
{"slave_id":1, "function_code":3, "offset":0, "number_of_registers":2, "format":"<f", "byte_swap":true}
```

### Address 

#### slave_id
    The slave ID

#### function_code
    01 (0x01) Read Coils
    02 (0x02) Read Discrete Inputs
    03 (0x03) Read Holding Registers
    04 (0x04) Read Input Registers
    23 (0x17) Read/Write Multiple registers

#### offset
    The starting register address specified in the Request PDU

#### number_of_registers
    The number of registers specified in the Request PDU

#### format
Use python3 library struct to format bytes.
Python bytes objects are used to hold the data representing the C struct
and also as format strings (explained below) to describe the layout of data in the C struct.

The optional first format char indicates byte order, size and alignment:
    @: native order, size & alignment (default)
    =: native order, std. size & alignment
    <: little-endian, std. size & alignment
    >: big-endian, std. size & alignment
    !: same as >

The remaining chars indicate types of args and must match exactly;
these can be preceded by a decimal repeat count:
    x: pad byte (no data); c:char; b:signed byte; B:unsigned byte;
    ?: _Bool (requires C99; if not available, char is used instead)
    h:short; H:unsigned short; i:int; I:unsigned int;
    l:long; L:unsigned long; f:float; d:double.

Special cases (preceding decimal count indicates length):
    s:string (array of char); p: pascal string (with count byte).
Special cases (only available in native format):
    n:ssize_t; N:size_t;
    P:an integer type that is wide enough to hold a pointer.

Special case (not in native mode unless 'long long' in platform C):
    q:long long; Q:unsigned long long

Whitespace between formats is ignored.

#### byte_swap
A boolean indicates whether or not to swap adjacent bytes.  
Swap adjacent bytes of 32bits(4bytes) or 64bits(8bytes).
This is not for little-endian and big-endian swapping, and use format for that.
The option is effective when number_of_registers is ether 2(32bits) or 4(64bits), 
else it will be ignored.


### References
  [1]. http://myems.io
  
  [2]. http://www.modbus.org/tech.php
  
  [3]. https://github.com/ljean/modbus-tk

  [4]. https://docs.python.org/3/library/struct.html#format-strings