from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from core.money import rounded

FONTS = Path(reportlab.__file__).parent / 'fonts'
pdfmetrics.registerFont(TTFont('Qavelys', str(FONTS / 'Vera.ttf')))
pdfmetrics.registerFont(TTFont('QavelysBold', str(FONTS / 'VeraBd.ttf')))
pdfmetrics.registerFontFamily('Qavelys', normal='Qavelys', bold='QavelysBold')


def text(value):
    value = ''.join(char for char in str(value or '') if ord(char) >= 32 or char in '\n\t')
    return escape(value).replace('\n', '<br/>')


def number(value):
    value = format(value, 'f')
    return value.rstrip('0').rstrip('.') if '.' in value else value


def financial_pdf(obj, kind):
    invoice = obj if kind == 'invoices' else obj.invoice
    output = BytesIO(); width = A4[0] - 84
    styles = getSampleStyleSheet()
    base = ParagraphStyle('QBase', fontName='Qavelys', fontSize=9, leading=13, textColor=colors.HexColor('#0F172A'), spaceAfter=4, splitLongWords=True)
    small = ParagraphStyle('QSmall', parent=base, fontSize=7.5, leading=10)
    title = ParagraphStyle('QTitle', parent=base, fontName='QavelysBold', fontSize=21, leading=26, spaceAfter=8)
    label = ParagraphStyle('QLabel', parent=base, fontName='QavelysBold', textColor=colors.HexColor('#6D5DF5'))
    right = ParagraphStyle('QRight', parent=small, alignment=TA_RIGHT)
    p = lambda value, style=base: Paragraph(text(value), style)
    story = [p('Qavelys', label), p('FACTURE CLIENT' if kind == 'invoices' else 'AVOIR CLIENT', title), p(obj.reference, label), p(f'Émission : {obj.issue_date:%d/%m/%Y}' + (f'   |   Échéance : {invoice.due_date:%d/%m/%Y}' if kind == 'invoices' else f'   |   Facture : {invoice.reference}')), Spacer(1, 12)]
    issuer, partner = invoice.issuer_snapshot, invoice.partner_snapshot
    addresses = Table([[p('ÉMETTEUR', label), p('CLIENT', label)], [p(issuer.get('name', '')), p(partner.get('name', ''))], [p(issuer.get('address', '')), p(partner.get('address', ''))], [p(issuer.get('phone', '')), p(partner.get('email', ''))]], colWidths=[width / 2] * 2, hAlign='LEFT')
    addresses.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 14), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
    story.extend([addresses, Spacer(1, 16)])
    if kind == 'credit-notes': story.extend([p('Motif de l’avoir', label), p(obj.reason), Spacer(1, 8)])
    if kind == 'invoices':
        columns = [width - 288, 38, 75, 45, 45, 85]
        data = [[p(value, small) for value in ['Description', 'Qté', 'Prix HT', 'Remise', 'Taxe', 'HT exact']]]
        for line in obj.lines.order_by('position'):
            data.append([p(line.description, small), p(number(line.quantity), right), p(number(line.unit_price), right), p(number(line.discount_rate) + ' %', right), p(number(line.tax_rate) + ' %', right), p(number(line.line_total), right)])
    else:
        columns = [width - 160, 60, 100]
        data = [[p(value, small) for value in ['Description', 'Quantité', 'HT exact']]]
        for line in obj.lines.select_related('invoice_line').order_by('invoice_line__position'):
            data.append([p(line.invoice_line.description, small), p(number(line.quantity), right), p(number(line.amount), right)])
    table = Table(data, colWidths=columns, repeatRows=1, splitByRow=1, splitInRow=1, hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EEEAFE')), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LINEBELOW', (0, 0), (-1, 0), .6, colors.HexColor('#6D5DF5')), ('LINEBELOW', (0, 1), (-1, -1), .25, colors.HexColor('#E2E8F0')), ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6), ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
    story.extend([table, Spacer(1, 16)])
    totals = [[p(name), p(f'{rounded(value, obj.currency_code):f} {obj.currency_code}', right)] for name, value in [('Total HT', obj.untaxed_amount), ('Taxes', obj.tax_amount), ('Total TTC', obj.total_amount)]]
    totals_table = Table(totals, colWidths=[130, 130], hAlign='RIGHT')
    totals_table.setStyle(TableStyle([('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#EEEAFE')), ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    story.append(KeepTogether([totals_table, Spacer(1, 8)]))
    story.append(p('Calculs exacts par ligne ; arrondi appliqué au total du document.' if kind == 'invoices' else 'Montants de cet avoir calculés par variation des totaux cumulés arrondis ; les HT exacts des lignes ne servent pas à additionner les totaux affichés.', small))
    if obj.notes: story.extend([Spacer(1, 10), p('Notes', label), p(obj.notes)])
    def footer(canvas, document):
        canvas.saveState(); canvas.setFont('Qavelys', 7); canvas.setFillColor(colors.HexColor('#64748B'))
        canvas.drawString(42, 25, f'Qavelys - {obj.reference}'); canvas.drawRightString(A4[0] - 42, 25, f'Page {document.page}'); canvas.restoreState()
    SimpleDocTemplate(output, pagesize=A4, leftMargin=42, rightMargin=42, topMargin=36, bottomMargin=42, title=obj.reference, author=issuer.get('name', 'Qavelys')).build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
