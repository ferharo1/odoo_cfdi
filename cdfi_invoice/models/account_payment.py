# -*- coding: utf-8 -*-

import base64
import json
import requests
from lxml import etree
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from . import amount_to_text_es_MX
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.lib.units import mm

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    forma_pago = fields.Selection(selection=[('01', _('Efectivo')),
                                         ('02', _('Cheque')),
                                         ('03', _('Transferencia')),
                                         ('04', _('Tarjeta de crédito')),
                                         ('28', _('Tarjeta de débito')),
                                           ],
                                string=_('Forma de pago'), 
                            )
    tipo_comprobante = fields.Selection(
                                selection=[ ('P', 'Pago'),],
                                string=_('Tipo de comprobante'),
                            )
    methodo_pago = fields.Selection(
        selection=[('PUE', _('Pago en una sola exhibición')),
                   ('PPD', _('Pago en parcialidades o diferido')),],
        string=_('Método de pago'), 
    )
    no_de_pago = fields.Integer("No. de pago", readonly=True)
    saldo_pendiente = fields.Float("Saldo pendiente", readonly=True)
    monto_pagar = fields.Float("Monto a pagar", compute='_compute_monto_pagar')
    saldo_restante = fields.Float("Saldo restante", readonly=True)
    fecha_pago = fields.Datetime("Fecha de pago")
    cuenta_emisor = fields.Many2one('res.partner.bank', string=_('Cuenta del emisor'))
    banco_emisor = fields.Char("Banco del emisor", related='cuenta_emisor.bank_name', readonly=True)
    rfc_banco_emisor = fields.Char(_("RFC banco emisor"), related='cuenta_emisor.bank_bic', readonly=True)
    numero_operacion = fields.Char(_("Número de operación"))
    banco_receptor = fields.Char(_("Banco receptor"), compute='_compute_banco_receptor')
    cuenta_beneficiario = fields.Char(_("Cuenta beneficiario"), compute='_compute_banco_receptor')
    rfc_banco_receptor = fields.Char(_("RFC banco receptor"), compute='_compute_banco_receptor')
    estado_pago = fields.Selection(
        selection=[('pago_no_enviado', 'Pago no enviado'), 
                   ('pago_correcto', 'Pago correcto'), 
                   ('problemas_pago', 'Problemas con el pago'), ],
        string=_('Estado de pago'),
        default='pago_no_enviado',
        readonly=True
    )
    tipo_relacion = fields.Selection(
        selection=[('04', 'Sustitución de los CFDI previos'),],
        string=_('Tipo relación'),
    )
    uuid_relacionado = fields.Char(string=_('CFDI Relacionado'))
    confirmacion = fields.Char(string=_('Confirmación'))
    folio_fiscal = fields.Char(string=_('Folio Fiscal'), readonly=True)
    numero_cetificado = fields.Char(string=_('Numero de certificado'))
    cetificaso_sat = fields.Char(string=_('Cetificado SAT'))
    fecha_certificacion = fields.Char(string=_('Fecha y Hora Certificación'))
    cadena_origenal = fields.Char(string=_('Cadena Original del Complemento digital de SAT'))
    selo_digital_cdfi = fields.Char(string=_('Sello Digital del CDFI'))
    selo_sat = fields.Char(string=_('Sello del SAT'))
 #   moneda = fields.Char(string=_('Moneda'))
    monedap = fields.Char(string=_('Moneda'))
#    tipocambio = fields.Char(string=_('TipoCambio'))
    tipocambiop = fields.Char(string=_('TipoCambio'))
    folio = fields.Char(string=_('Folio'))
    version = fields.Char(string=_('Version'))
    number_folio = fields.Char(string=_('Folio'), compute='_get_number_folio')
    amount_to_text = fields.Char('Amount to Text', compute='_get_amount_to_text',
                                 size=256, 
                                 help='Amount of the invoice in letter')
    qr_value = fields.Char(string=_('QR Code Value'))
    qrcode_image = fields.Binary("QRCode")
    rfc_emisor = fields.Char(string=_('RFC'))
    name_emisor = fields.Char(string=_('Name'))
    xml_payment_link = fields.Char(string=_('XML link'), readonly=True)
    payment_mail_ids = fields.One2many('account.payment.mail', 'payment_id', string='Payment Mails')
    iddocumento = fields.Char(string=_('iddocumento'))
    fecha_emision = fields.Char(string=_('Fecha y Hora Certificación'))
    docto_relacionados = fields.Text("Docto relacionados",default='[]')
    
    @api.one
    @api.depends('name')
    def _get_number_folio(self):
        if self.number:
            self.number_folio = self.name.replace('CUST.IN','').replace('/','')

    @api.model
    def get_docto_relacionados(self,payment):
        try:
            data = json.loads(payment.docto_relacionados)
        except Exception:
            data = []    
        return data

    @api.model
    def create(self, vals):
        res = super(AccountPayment, self).create(vals)
        if res.invoice_ids:
            docto_relacionados = []
            monto_pagado = round(res.monto_pagar,2)
            for invoice in res.invoice_ids:
                if monto_pagado > invoice.residual:
                    monto_pagar = round(invoice.residual,2)
                    monto_pagado -= round(invoice.residual,2)
                else:
                    monto_pagar = round(monto_pagado,2)
                docto_relacionados.append({
                      'moneda': invoice.moneda,
                      'tipodecambio': invoice.tipocambio,
                      'iddocumento': invoice.folio_fiscal,
                      'no_de_pago': len(invoice.payment_ids),
                      'saldo_pendiente': round(invoice.residual,2),
                      'monto_pagar': monto_pagar,
                      'saldo_restante': round((invoice.residual - monto_pagar),2),
                })
            saldo_pendiente = sum(inv.residual for inv in res.invoice_ids)
            res.write({'docto_relacionados': json.dumps(docto_relacionados), 'no_de_pago':sum(len(inv.payment_ids) for inv in res.invoice_ids),
                       'saldo_pendiente': saldo_pendiente, 'saldo_restante':saldo_pendiente - res.monto_pagar})
        return res
            
    @api.one
    @api.depends('amount')
    def _compute_monto_pagar(self):
        if self.amount:
            self.monto_pagar = self.amount
            
    @api.one
    @api.depends('journal_id')
    def _compute_banco_receptor(self):
        if self.journal_id and self.journal_id.bank_id:
            self.banco_receptor = self.journal_id.bank_id.name
            self.rfc_banco_receptor = self.journal_id.bank_id.bic
        if self.journal_id:
            self.cuenta_beneficiario = self.journal_id.bank_acc_number
             
    @api.one
    @api.depends('amount', 'currency_id')
    def _get_amount_to_text(self):
        self.amount_to_text = amount_to_text_es_MX.get_amount_to_text(self, self.amount_total, 'es_cheque', self.currency_id.name)
        
    @api.model
    def _get_amount_2_text(self, amount_total):
        return amount_to_text_es_MX.get_amount_to_text(self, amount_total, 'es_cheque', self.currency_id.name)
            
    @api.model
    def to_json(self):
        if not self.company_id.archivo_cer:
            raise UserError(_('Archivo .cer path is missing.'))
        if not self.company_id.archivo_key:
            raise UserError(_('Archivo .key path is missing.'))
        archivo_cer = self.company_id.archivo_cer
        archivo_key = self.company_id.archivo_key
        self.monedap = self.currency_id.name
        if self.currency_id.name == 'MXN':
            self.tipocambiop = '1'
        else:
            self.tipocambiop = self.currency_id.rate
        self.methodo_pago  = 'PPD'

        if self.invoice_ids:		            
            request_params = { 
                'company': {
                      'rfc': self.company_id.rfc,
                      'api_key': self.company_id.proveedor_timbrado,
                      'modo_prueba': self.company_id.modo_prueba,
                      'regimen_fiscal': self.company_id.regimen_fiscal,
                      'postalcode': self.company_id.zip,
                      'nombre_fiscal': self.company_id.nombre_fiscal,
                      'telefono_sms': self.company_id.telefono_sms,
                },
                'customer': {
                      'name': self.partner_id.name,
                      'rfc': self.partner_id.rfc,
                      'uso_cfdi': 'P01',
                },
                'invoice': {
                      'tipo_comprobante': self.tipo_comprobante,
                      'folio_complemento': self.name.replace('CUST.IN','').replace('/',''),
                      'serie_complemento': self.company_id.serie_complemento,
                },
                'concept': {
                      'claveprodserv': '84111506',
                      'calveunidad': 'ACT',
                      'cantidad': 1,
                      'descripcion': 'Pago',
                },
                'payment': {
                      'moneda': self.currency_id.name,
                      'tipocambio': self.currency_id.rate,
                      'forma_pago': self.forma_pago,
                      'numero_operacion': self.numero_operacion,
                      'banco_emisor': self.banco_emisor,
                      'cuenta_emisor': self.cuenta_emisor and self.cuenta_emisor.acc_number or '',
                      'rfc_banco_emisor': self.rfc_banco_emisor,
                      'banco_receptor': self.banco_receptor,
                      'cuenta_beneficiario': self.cuenta_beneficiario,
                      'rfc_banco_receptor': self.rfc_banco_receptor,
                      'fecha_pago': self.fecha_pago,
                      'monto_factura':  self.amount
                },

                'docto_relacionado': json.loads(self.docto_relacionados),
                'adicional': {
                      'tipo_relacion': self.tipo_relacion,
                      'uuid_relacionado': self.uuid_relacionado,
                      'confirmacion': self.confirmacion,					  
                },				
                'certificados': {
                      'archivo_cer': archivo_cer.decode("utf-8"),
                      'archivo_key': archivo_key.decode("utf-8"),
                      'contrasena': self.company_id.contrasena,
                }
            }
        else:
            request_params = { 
                'company': {
                      'rfc': self.company_id.rfc,
                      'api_key': self.company_id.proveedor_timbrado,
                      'modo_prueba': self.company_id.modo_prueba,
                      'regimen_fiscal': self.company_id.regimen_fiscal,
                      'postalcode': self.company_id.zip,
                      'nombre_fiscal': self.company_id.nombre_fiscal,
                },
                'customer': {
                      'name': self.partner_id.name,
                      'rfc': self.partner_id.rfc,
                      'uso_cfdi': 'P01',
                },
                'invoice': {
                      'tipo_comprobante': self.tipo_comprobante,
                      'folio_complemento': self.name.replace('CUST.IN','').replace('/',''),
                      'serie_complemento': self.company_id.serie_complemento,
                },
                'concept': {
                      'claveprodserv': '84111506',
                      'calveunidad': 'ACT',
                      'cantidad': 1,
                      'descripcion': 'Pago',
                },
                'payment': {
                      'moneda': self.currency_id.name,
                      'tipocambio': self.currency_id.rate,
                      'forma_pago': self.forma_pago,
                      'numero_operacion': self.numero_operacion,
                      'banco_emisor': self.banco_emisor,
                      'cuenta_emisor': self.cuenta_emisor and self.cuenta_emisor.acc_number or '',
                      'rfc_banco_emisor': self.rfc_banco_emisor,
                      'banco_receptor': self.banco_receptor,
                      'cuenta_beneficiario': self.cuenta_beneficiario,
                      'rfc_banco_receptor': self.rfc_banco_receptor,
                      'fecha_pago': self.fecha_pago,
                      'monto_factura': self.amount,
                },
                'docto_relacionado': [{
                      'moneda': 'false',
                      'tipodecambio': 'false',
                      'iddocumento': 'false',
                      'no_de_pago': 'false',
                      'saldo_pendiente': 'false',
                      'monto_pagar': 'false',
                      'saldo_restante': 'false',
                }],
                'adicional': {
                      'tipo_relacion': self.tipo_relacion,
                      'uuid_relacionado': self.uuid_relacionado,
                      'confirmacion': self.confirmacion,					  
                },				
                'certificados': {
                      'archivo_cer': archivo_cer.decode("utf-8"),
                      'archivo_key': archivo_key.decode("utf-8"),
                      'contrasena': self.company_id.contrasena,
                }		
            }
        return request_params
    
    @api.multi
    def complete_payment(self):
        for p in self:
            values = p.to_json()
            if self.company_id.proveedor_timbrado == 'multifactura':
                url = '%s' % ('http://facturacion.itadmin.com.mx/api/payment')
            elif self.company_id.proveedor_timbrado == 'gecoerp':
                if self.company_id.modo_prueba:
                    #url = '%s' % ('https://ws.gecoerp.com/itadmin/pruebas/payment/?handler=OdooHandler33')
                    url = '%s' % ('https://itadmin.gecoerp.com/payment2/?handler=OdooHandler33')
                else:
                    url = '%s' % ('https://itadmin.gecoerp.com/payment2/?handler=OdooHandler33')
            response = requests.post(url , 
                                     auth=None,verify=False, data=json.dumps(values), 
                                     headers={"Content-type": "application/json"})

            #print 'Response: ', response.status_code
            json_response = response.json()
            xml_file_link = False
            estado_pago = json_response['estado_pago']
            if estado_pago == 'problemas_pago':
                raise UserError(_(json_response['problemas_message']))
            # Receive and stroe XML 
            if json_response.get('pago_xml'):
                xml_file_link = p.company_id.factura_dir + '/' + p.name.replace('/', '_') + '.xml'
                xml_file = open(xml_file_link, 'w')
                xml_payment = base64.b64decode(json_response['pago_xml'])
                xml_file.write(xml_payment.decode("utf-8"))
                xml_file.close()
                p._set_data_from_xml(xml_payment)
                    
                xml_file_name = p.name.replace('/', '_') + '.xml'
                self.env['ir.attachment'].sudo().create(
                                            {
                                                'name': xml_file_name,
                                                'datas': json_response['pago_xml'],
                                                'datas_fname': xml_file_name,
                                                'res_model': self._name,
                                                'res_id': p.id,
                                                'type': 'binary'
                                            })	
                report = self.env['ir.actions.report']._get_report_from_name('cdfi_invoice.report_payment')
                report_data = report.render_qweb_pdf([p.id])[0]
                pdf_file_name = p.name.replace('/', '_') + '.pdf'
                self.env['ir.attachment'].sudo().create(
                                            {
                                                'name': pdf_file_name,
                                                'datas': base64.b64encode(report_data),
                                                'datas_fname': pdf_file_name,
                                                'res_model': self._name,
                                                'res_id': p.id,
                                                'type': 'binary'
                                            })

            p.write({'estado_pago': estado_pago,
                    'xml_payment_link': xml_file_link})
            
    @api.multi
    def validate_complete_payment(self):
        self.post()
        return {
            'name': _('Payments'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.payment',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'res_id': self.id,
        }

    @api.one
    def _set_data_from_xml(self, xml_payment):
        if not xml_payment:
            return None
        NSMAP = {
                 'xsi':'http://www.w3.org/2001/XMLSchema-instance',
                 'cfdi':'http://www.sat.gob.mx/cfd/3', 
                 'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital',
                 'pago10': 'http://www.sat.gob.mx/Pagos',
                 }
        xml_data = etree.fromstring(xml_payment)
        Emisor = xml_data.find('cfdi:Emisor', NSMAP)
        RegimenFiscal = Emisor.find('cfdi:RegimenFiscal', NSMAP)
        Complemento = xml_data.find('cfdi:Complemento', NSMAP)
        TimbreFiscalDigital = Complemento.find('tfd:TimbreFiscalDigital', NSMAP)
        Pagos = Complemento.find('pago10:Pagos', NSMAP)
        Pago = Pagos.find('pago10:Pago', NSMAP)
        DoctoRelacionado = Pago.find('pago10:DoctoRelacionado', NSMAP)
        self.rfc_emisor = Emisor.attrib['Rfc']
        self.name_emisor = Emisor.attrib['Nombre']
#        if self.invoice_ids:
#           self.methodo_pago = DoctoRelacionado.attrib['MetodoDePagoDR']
#           self.moneda = DoctoRelacionado.attrib['MonedaDR']
#           self.monedap = Pago.attrib['MonedaP']
#           if self.monedap != 'MXN':		   
#               self.tipocambiop = Pago.attrib['TipoCambioP']	   
#           if self.moneda != self.monedap:
#                 self.tipocambio = DoctoRelacionado.attrib['TipoCambioDR']
#           self.iddocumento = DoctoRelacionado.attrib['IdDocumento']
        self.numero_cetificado = xml_data.attrib['NoCertificado']
        self.fecha_emision = xml_data.attrib['Fecha']
        self.cetificaso_sat = TimbreFiscalDigital.attrib['NoCertificadoSAT']
        self.fecha_certificacion = TimbreFiscalDigital.attrib['FechaTimbrado']
        self.selo_digital_cdfi = TimbreFiscalDigital.attrib['SelloCFD']
        self.selo_sat = TimbreFiscalDigital.attrib['SelloSAT']
        self.folio_fiscal = TimbreFiscalDigital.attrib['UUID']
        self.folio = xml_data.attrib['Folio']     
        self.invoice_datetime = xml_data.attrib['Fecha']
        self.version = TimbreFiscalDigital.attrib['Version']
        self.cadena_origenal = '||%s|%s|%s|%s|%s||' % (self.version, self.folio_fiscal, self.fecha_certificacion, 
                                                         self.selo_digital_cdfi, self.cetificaso_sat)
        
        options = {'width': 275 * mm, 'height': 275 * mm}
        amount_str = str(self.amount).split('.')
        qr_value = '?re=%s&rr=%s&tt=%s.%s&id=%s' % (self.company_id.rfc, 
                                                 self.partner_id.rfc,
                                                 amount_str[0].zfill(10),
                                                 amount_str[1].ljust(6, '0'),
                                                 self.folio_fiscal
                                                 )
        self.qr_value = qr_value
        ret_val = createBarcodeDrawing('QR', value=qr_value, **options)
        self.qrcode_image = base64.encodestring(ret_val.asString('jpg'))
        self.folio_fiscal = TimbreFiscalDigital.attrib['UUID']
        
    @api.multi
    def send_payment(self):
        self.ensure_one()
        template = self.env.ref('cdfi_invoice.email_template_payment', False)
        compose_form = self.env.ref('mail.email_compose_message_wizard_form', False)
            
        ctx = dict()
        ctx.update({
            'default_model': 'account.payment',
            'default_res_id': self.id,
            'default_use_template': bool(template),
            'default_template_id': template.id,
            'default_composition_mode': 'comment',
        })
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }

class AccountPaymentMail(models.Model):
    _name = "account.payment.mail"
    _inherit = ['mail.thread']
    _description = "Payment Mail"
    
    payment_id = fields.Many2one('account.payment', string='Payment')
    name = fields.Char(related='payment_id.name')
    xml_payment_link = fields.Char(related='payment_id.xml_payment_link')
    partner_id = fields.Many2one(related='payment_id.partner_id')
    company_id = fields.Many2one(related='payment_id.company_id')
    
class MailTemplate(models.Model):
    "Templates for sending email"
    _inherit = 'mail.template'
    
    @api.model
    def _get_file(self, url):
        url = url.encode('utf8')
        filename, headers = urllib.urlretrieve(url)
        fn, file_extension = os.path.splitext(filename)
        return  filename, file_extension.replace('.', '')

    @api.multi
    def generate_email(self, res_ids, fields=None):
        results = super(MailTemplate, self).generate_email(res_ids, fields=fields)
        
        if isinstance(res_ids, (int)):
            res_ids = [res_ids]
        res_ids_to_templates = super(MailTemplate, self).get_email_template(res_ids)

        # templates: res_id -> template; template -> res_ids
        templates_to_res_ids = {}
        for res_id, template in res_ids_to_templates.items():
            templates_to_res_ids.setdefault(template, []).append(res_id)
        
        template_id = self.env.ref('cdfi_invoice.email_template_payment')
        for template, template_res_ids in templates_to_res_ids.items():
            if template.id  == template_id.id:
                for res_id in template_res_ids:
                    payment = self.env[template.model].browse(res_id)
                    if payment.xml_payment_link:
                        attachments =  results[res_id]['attachments'] or []
                        names = payment.xml_payment_link.split('/')
                        fn = names[len(names) - 1]
                        data = open(payment.xml_payment_link, 'rb').read()
                        attachments.append((fn, base64.b64encode(data)))
                        results[res_id]['attachments'] = attachments
        return results

class AccountPaymentTerm(models.Model):
    "Terminos de pago"
    _inherit = "account.payment.term"

    methodo_pago = fields.Selection(
        selection=[('PUE', _('Pago en una sola exhibición')),
                   ('PPD', _('Pago en parcialidades o diferido')),],
        string=_('Método de pago'), 
    )

    forma_pago = fields.Selection(
        selection=[('01', '01 - Efectivo'), 
                   ('02', '02 - Cheque nominativo'), 
                   ('03', '03 - Transferencia electrónica de fondos'),
                   ('04', '04 - Tarjeta de Crédito'), 
                   ('05', '05 - Monedero electrónico'),
                   ('06', '06 - Dinero electrónico'), 
                   ('08', '08 - Vales de despensa'), 
                   ('12', '12 - Dación en pago'), 
                   ('13', '13 - Pago por subrogación'), 
                   ('14', '14 - Pago por consignación'), 
                   ('15', '15 - Condonación'), 
                   ('17', '17 - Compensación'), 
                   ('23', '23 - Novación'), 
                   ('24', '24 - Confusión'), 
                   ('25', '25 - Remisión de deuda'), 
                   ('26', '26 - Prescripción o caducidad'), 
                   ('27', '27 - A satisfacción del acreedor'), 
                   ('28', '28 - Tarjeta de débito'), 
                   ('29', '29 - Tarjeta de servicios'), 
                   ('30', '30 - Aplicación de anticipos'), 
                   ('99', '99 - Por definir'),],
        string=_('Forma de pago'),
    )