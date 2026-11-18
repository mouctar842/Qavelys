import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path
from rest_framework.exceptions import ValidationError

_CATALOG = json.loads((Path(__file__).resolve().parent.parent / 'config/data/currencies.json').read_text(encoding='utf-8'))
CURRENCIES = {item['code']: item for item in _CATALOG['currencies']}


def decimal(value):
    if isinstance(value, float):
        raise ValidationError('Les montants doivent être transmis comme chaînes décimales.')
    try:
        result = Decimal(value)
    except (ValueError, TypeError, InvalidOperation):
        raise ValidationError('Valeur décimale invalide.')
    if not result.is_finite():
        raise ValidationError('Valeur décimale non finie.')
    return result


def quantum(currency):
    if currency not in CURRENCIES:
        raise ValidationError('Devise inconnue ou sans précision monétaire définie.')
    return Decimal(1).scaleb(-CURRENCIES[currency]['digits'])


def rounded(amount, currency):
    with localcontext() as ctx:
        ctx.prec = 60
        return decimal(amount).quantize(quantum(currency), rounding=ROUND_HALF_UP)


def exact_line(quantity, unit_price, discount_rate='0', tax_rate='0'):
    with localcontext() as ctx:
        ctx.prec = 60
        quantity, price, discount, tax = map(decimal, [quantity, unit_price, discount_rate, tax_rate])
        if quantity <= 0 or price < 0 or not 0 <= discount <= 100 or not 0 <= tax <= 100:
            raise ValidationError('Quantité, prix, remise ou taux de taxe invalide.')
        net = quantity * price * (Decimal(1) - discount / 100)
        return net, net * tax / 100


def document_totals(lines, currency):
    with localcontext() as ctx:
        ctx.prec = 60
        net, tax = Decimal(0), Decimal(0)
        for line in lines:
            line_net, line_tax = exact_line(line['quantity'], line['unit_price'], line.get('discount_rate', '0'), line.get('tax_rate', '0'))
            net += line_net
            tax += line_tax
        net, tax = rounded(net, currency), rounded(tax, currency)
        return {'untaxed_amount': net, 'tax_amount': tax, 'total_amount': net + tax}
