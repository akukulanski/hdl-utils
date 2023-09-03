from amaranth.hdl.rec import Record, DIR_FANIN, DIR_FANOUT


__all__ = ['DataStreamMaster', 'DataStreamSlave']


def to_direction(interface, d):
    assert interface in ['master', 'slave']
    assert d in ['m_to_s', 's_to_m']

    if interface == 'master':
        return DIR_FANOUT if d == 'm_to_s' else DIR_FANIN
    else:
        return DIR_FANOUT if d == 's_to_m' else DIR_FANIN


def get_stream_layout(interface, data_w):
    assert interface in ['master', 'slave']
    layout = [
        ("valid", 1, "m_to_s"),
        ("last", 1, "m_to_s"),
        ("data", data_w, "m_to_s"),
        ("ready", 1, "s_to_m"),
    ]
    return [(f, w, to_direction(interface, d)) for f, w, d in layout]


def connect_m2s(master, slave, exclude=None):
    exclude = exclude or ()
    layout = [(k, v[1]) for k, v in master.layout.fields.items()]
    ret = [master[f].eq(slave[f])
           for f, d in layout if d == DIR_FANIN
           if f not in exclude]
    ret += [slave[f].eq(master[f])
            for f, d in layout if d == DIR_FANOUT
            if f not in exclude]
    return ret


class DataStreamBase(Record):

    direction = None

    def __init__(self, data_w, **kargs):
        layout = get_stream_layout(self.direction, data_w)
        Record.__init__(self, layout, **kargs)

    def data_w(self):
        return len(self.data)

    def accepted(self):
        return self.valid & self.ready

    @classmethod
    def from_record(cls, rec, **kwargs):
        return cls(len(rec.data), fields=rec.fields, **kwargs)


class DataStreamMaster(DataStreamBase):

    direction = 'master'

    def connect(self, slave):
        assert isinstance(slave, DataStreamSlave)
        return connect_m2s(self, slave)

    def as_slave(self):
        name = self.name + '_as_slave' if self.name else None
        return DataStreamSlave.from_record(self, name=name)


class DataStreamSlave(DataStreamBase):

    direction = 'slave'

    def connect(self, master):
        assert isinstance(master, DataStreamSlave)
        return connect_m2s(master, self)

    def as_master(self):
        name = self.name + '_as_master' if self.name else None
        return DataStreamMaster.from_record(self, name=name)
