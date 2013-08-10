class AbstractDataType(object):
    def __init__(self, name):
        self.name = name
        self.fixedSize = True

    def parse(self, cursor):
        """Should return Value structure"""
        raise NotImplementedError()


class Integer(AbstractDataType):
    def __init__(self, binary_format, signed=True):
        pass

    def parse(self, cursor):
        return struct.unpack(...)


class ZeroString(AbstractDataType):
    def __init__(self, encoding):
        pass

    def parse(self, cursor):
        offset = 0
        while not cursor.atEnd(offset) and cursor[offset] != 0:
            pass
        return self.fromEncoding(cursor[:offset])


class PascalString(AbstractDataType):
    def __init__(self, encoding):
        pass

    def parse(self, cursor):
        string_length = Integer(signed=False).parse(cursor).value
        return self.fromEncoding(cursor[:string_length])


class Win32_UnicodeString(AbstractDataType):
    pass


class Enumeration(AbstractDataType):
    def __init__(self, primary_type, members):
        pass

    def parse(self, cursor):
        value = self.primaryType.parse(cursor).value
        if value in self.members:
            return self.members[value]


class Structure(AbstractDataType):
    def __init__(self, members):
        pass

