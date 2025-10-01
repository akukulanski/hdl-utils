from hdl_utils.amaranth_utils.reg_map import Field, Register, RegisterMapFactory


def get_example_reg_map_factory(data_w: int) -> RegisterMapFactory:
    reg_map_factory = RegisterMapFactory(reg_width=data_w)
    reg_map_factory.allocate_registers([
        Register(
            name='reg_rw_1',
            dir='rw',
            # force_addr=0x00000000,
            fields=[
                Field(name='field_1', width=32, offset= 0),
            ],
        ),
        Register(
            name='reg_rw_2',
            dir='rw',
            # force_addr=0x00000004,
            fields=[
                Field(name='field_2', width= 1, offset= 0),
                Field(name='field_3', width=15, offset= 1),
                Field(name='field_4', width=16, offset=16),
            ],
        ),
        Register(
            name='reg_rw_3',
            dir='rw',
            # force_addr=0x00000008,
            fields=[
                Field(name='field_5', width=32, offset= 0),
            ],
        ),
        Register(
            name='reg_ro_1',
            dir='ro',
            # force_addr=0x0000000C,
            fields=[
                Field(name='field_10', width=32, offset= 0),
            ],
        ),
        Register(
            name='reg_ro_2',
            dir='ro',
            # force_addr=0x00000010,
            fields=[
                Field(name='field_20', width= 1, offset= 0),
                Field(name='field_30', width=15, offset= 1),
                Field(name='field_40', width=16, offset=16),
            ],
        ),
        Register(
            name='reg_ro_3',
            dir='ro',
            # force_addr=0x00000014,
            fields=[
                Field(name='field_50', width=32, offset= 0),
            ],
        ),
    ])
    return reg_map_factory
