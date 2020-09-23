"""Scripts for upload order files to sftp."""
from ..models import VtexClientOrder, VtexClientOrderItem, paramiko


paramiko.util.log_to_file("paramiko.log")

def run():
    orders_from_api = VtexClientOrder.get_orders()
    orders_from_db = VtexClientOrder.factory(orders_from_api[0:3])
    VtexClientOrderItem.factory(orders_from_db)
    VtexClientOrder.upload_to_sftp(orders_from_db)

