"""Order models."""
from datetime import datetime, timedelta
from typing import List

import paramiko
import requests
from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel


class Order(TimeStampedModel):
    """Order model."""

    order_type = models.CharField(verbose_name=_("tipo"), max_length=1)
    client_code = models.CharField(verbose_name=_("código del tercero"), max_length=128)
    file_type = models.CharField(verbose_name=_("tipo de archivo"), max_length=128)
    company_code = models.CharField(verbose_name=_("compañia"), max_length=12)
    order_created_at = models.DateTimeField(verbose_name=_("fecha de la orden"))
    shipping_stimate_date = models.DateTimeField(
        verbose_name=_("fecha planificada de entrega")
    )
    currency = models.CharField(verbose_name=_("moneda"), max_length=3)
    buyer_fullname = models.CharField(
        verbose_name=_("nombre del comprador"), max_length=512
    )
    buyer_document = models.CharField(
        verbose_name=_("documento del comprador"), max_length=512
    )
    buyer_phone = models.CharField(
        verbose_name=_("teléfono del comprador"), max_length=512
    )
    buyer_email = models.EmailField(verbose_name=_("email del comprador"))
    shipping_address = models.TextField(verbose_name=_("dirección de envío"))
    shipping_address_city = models.TextField(verbose_name=_("ciudad de envío"))
    shipping_address_reference = models.TextField(
        verbose_name=_("referencia de dirección de envío")
    )
    shipping_address_zip = models.TextField(verbose_name=_("código postal"))
    warehouse_code = models.CharField(
        verbose_name=_("codDIrección de la cabecera"), max_length=128
    )
    order_number = models.CharField(verbose_name=_("No. pedido"), max_length=30)
    sell_type = models.CharField(verbose_name=_("tipo de venta"), max_length=56)
    sell_type_code = models.CharField(
        verbose_name=_("código tipo de venta"), max_length=56
    )
    payment_proof = models.CharField(
        verbose_name=_("Comprobante de pago"), max_length=56
    )
    seller_code = models.CharField(verbose_name=_("código del vendedor"), max_length=56)
    route_text_code = models.CharField(
        verbose_name=_("codTextoRuta"), max_length=56, blank=True, null=True
    )
    from_api = JSONField()

    @staticmethod
    def erp_strftime(date: datetime = None) -> str:
        """Format date for erp file."""
        if date is None:
            return ""
        return datetime.strftime(date, "%d%m%Y")

    @staticmethod
    def ws_strptime(date: str) -> datetime:
        """
        Parse and format date received from webservice to datetime.

            - Remove microseconds and Timezone from str date
            - Parse str date to datetime
        """
        return datetime.strptime(date.split(".")[0], "%Y-%m-%dT%H:%M:%S")

    @staticmethod
    def get_orders_filter_hours_range(
        from_time: datetime = None, to_time: datetime = None
    ) -> str:
        """Get order filters hours range."""
        hours_range_format = "%Y-%m-%dT%H:%M:%S.%fZ"
        if from_time is None:
            from_time = datetime.utcnow()
        if to_time is None:
            to_time = datetime.utcnow() - timedelta(hours=1)
        hours_range = {
            "from": datetime.strftime(from_time, hours_range_format),
            "to": datetime.strftime(to_time, hours_range_format),
        }
        return f'creationDate:[{hours_range["from"]} TO {hours_range["to"]}]'

    def __str__(self):
        """Custom string representation."""
        return f"{self.order_number} - {self.buyer_fullname} - {self.order_created_at}"


class OrderItem(TimeStampedModel):
    """Order item model."""

    class TaxCode(models.TextChoices):
        """Cheese firmness."""

        ZERO = ("000", _("0%"))
        IVA = ("001", _("19%"))

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE)
    item_type = models.CharField(verbose_name=_("tipo"), max_length=1)
    item_number = models.IntegerField(verbose_name=_("consecutivo item"))
    ean = models.CharField(verbose_name=_("EAN"), max_length=56)
    item_qty = models.IntegerField(verbose_name=_("cantidad"))
    item_price_without_tax = models.FloatField(verbose_name=_("cantidad"), max_length=3)
    destination_address_code = models.CharField(
        verbose_name=_("Coddirección destino"), max_length=56
    )
    qty = models.IntegerField(verbose_name=_("cantidad 2"))
    tax_code = models.CharField(
        verbose_name=_("código fiscal"), max_length=3, choices=TaxCode.choices
    )


class VtexClientOrderItem(OrderItem):
    """Vtex client order model."""

    def __init__(self, *args, **kwargs):
        """Set vtex order default values."""
        kwargs["item_type"] = "D"
        kwargs["qty"] = 0
        kwargs["destination_address_code"] = ""
        # TODO verify if this field is dynamic
        kwargs["tax_code"] = OrderItem.TaxCode.IVA
        super().__init__(*args, **kwargs)

    @staticmethod
    def factory(orders_from_db: list):
        """Orders factory method."""
        objects = []
        for order in orders_from_db:
            for index, item in enumerate(order.from_api["items"]):
                defaults = {
                    "item_number": index + 1,
                    "item_qty": item["quantity"],
                    "item_price_without_tax": item["price"] // 100,
                }
                objects.append(
                    VtexClientOrderItem.objects.update_or_create(
                        order=order, ean=item["ean"], defaults=defaults
                    )[0]
                )
        return objects

    class Meta:
        """Set model as proxy."""

        proxy = True


class VtexClientOrder(Order):
    """Vtex client order model."""

    def __init__(self, *args, **kwargs):
        """Set vtex order default values."""
        kwargs["order_type"] = "H"
        kwargs["client_code"] = "CT0000344"
        kwargs["file_type"] = "E-COMM"
        kwargs["company_code"] = "120"
        kwargs["currency"] = "COP"
        kwargs["sell_type"] = "V010"
        kwargs["sell_type_code"] = "222"
        kwargs["payment_proof"] = ""
        kwargs["seller_code"] = "V02011"
        kwargs["route_text_code"] = ""
        # TODO warehouse_code is dynamic
        kwargs["warehouse_code"] = "CM0000001"
        super().__init__(*args, **kwargs)

    @staticmethod
    def get_orders(
        headers: dict = None, querystring: dict = None, page: int = 1
    ) -> list:
        """Get orders from vtex."""
        if headers is None:
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "x-vtex-api-appkey": settings.X_VTEX_API_APPKEY,
                "x-vtex-api-apptoken": settings.X_VTEX_API_APPTOKEN,
            }
        if querystring is None:
            querystring = {
                "f_creationDate": "creationDate:[2016-01-01T02:00:00.000Z TO 2021-01-01T01:59:59.999Z]",
            }
        querystring["page"] = page
        order_list_api_response = requests.request(
            "GET",
            settings.VTEX_ORDER_LIST_API_ENDPOINT,
            headers=headers,
            params=querystring,
        ).json()

        orders_list = [
            requests.request(
                "GET",
                settings.VTEX_ORDER_API_ENDPOINT + order_summary["orderId"],
                headers=headers,
            ).json()
            for order_summary in order_list_api_response["list"]
        ]

        current_page = order_list_api_response["paging"]["currentPage"]
        total_pages = order_list_api_response["paging"]["pages"]
        if current_page < total_pages:
            next_page = current_page + 1
            return orders_list + VtexClientOrder.get_orders(
                headers, querystring, page=next_page
            )

        return orders_list

    @staticmethod
    def format_ws_address_data(order: dict) -> dict:
        """Get dict addresses data."""
        address_data = order["shippingData"]["selectedAddresses"][0]
        address_info = " ".join(
            [
                address_data[info]
                for info in ["street", "number", "complement", "neighborhood"]
                if address_data.get(info)
            ]
        )
        return {
            "city": address_data.get("city"),
            "info": address_info,
            "reference": address_data.get("reference") or "",
            "postal_code": address_data.get("postalCode"),
        }

    @staticmethod
    def factory(orders_from_api: list):
        """Orders factory method."""
        objects = []
        for order in orders_from_api:
            address = VtexClientOrder.format_ws_address_data(order)
            defaults = {
                "order_created_at": VtexClientOrder.ws_strptime(order["creationDate"]),
                "shipping_stimate_date": VtexClientOrder.ws_strptime(
                    order["shippingData"]["logisticsInfo"][0]["shippingEstimateDate"]
                ),
                "buyer_fullname": f'{order["clientProfileData"]["firstName"]} {order["clientProfileData"]["lastName"]}',
                "buyer_document": order["clientProfileData"]["document"],
                "buyer_phone": order["clientProfileData"]["phone"],
                "buyer_email": order["clientProfileData"]["email"],
                "shipping_address": address["info"],
                "shipping_address_city": address["city"],
                "shipping_address_reference": address["reference"],
                "shipping_address_zip": address["postal_code"],
                "order_number": order["orderId"],
                "route_text_code": "",
                "from_api": order,
            }
            objects.append(
                VtexClientOrder.objects.update_or_create(
                    order_number=order["orderId"], defaults=defaults
                )[0]
            )
        return objects

    @staticmethod
    def get_file_headers(order: Order) -> list:
        """Get list of file headers."""
        return [
            f"{order.order_type}",  # Tipo
            f"|{order.client_code}",  # Código del tercero
            f"|{order.file_type}",  # Tipo de archivo
            f"|{order.company_code}",  # Compañia
            f"|{VtexClientOrder.erp_strftime(order.order_created_at)}",  # Fecha de la orden
            f"|{VtexClientOrder.erp_strftime(order.shipping_stimate_date)}",
            # Fecha planificada de entrega
            f"|{order.currency}",  # Moneda
            f"|{order.buyer_fullname}/{order.buyer_document}/{order.shipping_address_city}/{order.shipping_address}/{order.buyer_phone}/{order.shipping_address_reference}",
            # Texto
            "|1",  # 1
            f"|{order.warehouse_code}",  # CodDirección de la cabecera
            f"|{order.order_number}",  # No. pedido
            f"|?,{order.buyer_document},?,{order.buyer_fullname},{order.sell_type},{order.shipping_address_zip}",
            # Datos localización Colombia
            f"|{order.sell_type_code},{order.payment_proof}",  # Tipo de venta + Ref A
            f"|{order.seller_code}",  # Vendedor
            f"|{order.route_text_code}",  # CodTextoRuta
            f"|{order.buyer_email}",  # Correo electrónico
        ]

    @staticmethod
    def get_file_items(items: List[OrderItem]) -> list:
        """Get list of file item."""
        return [
            "".join(
                [
                    f"{item.item_type}",
                    f"|{item.item_number}",
                    f"|{item.ean}",
                    f"|{item.item_qty}",
                    f"|{item.item_price_without_tax}",
                    f"|{item.destination_address_code}|",
                    f"|{item.qty}",
                    f"|{item.tax_code}",
                ]
            )
            for item in items
        ]

    @staticmethod
    def create_order_files(sftp: paramiko.SFTPClient, orders: List[Order]):
        """Create order files."""
        for order in orders:
            print(order, "create_order_files")
            items = order.orderitem_set.all()
            file_path = f"ag-pruebas/{order.order_number}.txt"
            with sftp.file(file_path, "wt") as order_file:
                print("file", order_file)
                order_file.writelines(VtexClientOrder.get_file_headers(order))
                order_file.write("\n")
                order_file.writelines("\n".join(VtexClientOrder.get_file_items(items)))

    @staticmethod
    def upload_to_sftp(orders: List[Order]):
        """Upload a order list through sftp."""
        with paramiko.SSHClient() as ssh_client:
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh_client.connect(
                hostname=settings.SFTP_HOSTNAME,
                port=settings.SFTP_PORT,
                username=settings.SFTP_USERNAME,
                password=settings.SFTP_PASSWORD,
            )

            with ssh_client.open_sftp() as sftp:
                VtexClientOrder.create_order_files(sftp, orders)

    class Meta:
        """Set model as proxy."""

        proxy = True
