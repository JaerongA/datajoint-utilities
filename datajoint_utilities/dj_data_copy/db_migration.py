import datajoint as dj
import numpy as np


"""
Utility for same connection migration of data between schema and table
"""


def migrate_schema(origin_schema, destination_schema):
    """
    Data migration from all tables from `origin_schema` to `destination_schema`, in topologically sorted order
    """
    total_to_transfer_count = 0
    total_transferred_count = 0

    tbl_names = [tbl_name.split('.')[-1] for tbl_name in dj.Diagram(origin_schema).topological_sort()]
    tbl_names = ['.'.join([dj.utils.to_camel_case(s) for s in tbl_name.strip('`').split('__') if s])
                 for tbl_name in tbl_names]

    print(f'Data migration for schema: {origin_schema.schema.database}')

    for tbl_name in tbl_names:
        if '.' in tbl_name:
            master_name, part_name = tbl_name.split('.')
            orig_tbl = getattr(getattr(origin_schema, master_name), part_name)
            dest_tbl = getattr(getattr(destination_schema, master_name), part_name)
        else:
            orig_tbl = getattr(origin_schema, tbl_name)
            dest_tbl = getattr(destination_schema, tbl_name)

        transferred_count, to_transfer_count = migrate_table(orig_tbl, dest_tbl)
        total_transferred_count += transferred_count
        total_to_transfer_count += to_transfer_count

    print(f'--- Total records migrated: {total_transferred_count}/{total_to_transfer_count} records ---')
    return total_transferred_count, total_to_transfer_count


def migrate_table(orig_tbl, dest_tbl):
    """
    Migrate data from `orig_tbl` to `dest_tbl`
    """
    # check if the transfer is between different database servers (different db connections)
    is_different_server = orig_tbl.connection.conn_info['host'] != dest_tbl.connection.conn_info['host']

    # check if there's external datatype to be transferred
    has_external = np.any(['@' in attr.type
                           for attr in orig_tbl.heading.attributes.values()])

    if is_different_server:
        records_to_transfer = orig_tbl.proj() - (orig_tbl & dest_tbl.fetch('KEY')).proj()
    else:
        records_to_transfer = orig_tbl.proj() - dest_tbl.proj()

    to_transfer_count = len(records_to_transfer)

    try:
        if to_transfer_count:
            entries = ((orig_tbl & records_to_transfer).fetch(as_dict=True)
                       if has_external or is_different_server
                       else (orig_tbl & records_to_transfer))
            dest_tbl.insert(entries, skip_duplicates=True, allow_direct_insert=True)
    except dj.DataJointError as e:
        print(f'\tData copy error: {str(e)}')
        transferred_count = 0
    else:
        transferred_count = to_transfer_count

    print(f'\tData migration for table {orig_tbl.__name__}:'
          f' {transferred_count}/{to_transfer_count} records')
    return transferred_count, to_transfer_count