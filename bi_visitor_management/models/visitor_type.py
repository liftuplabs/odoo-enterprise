# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields


class VisitorType(models.Model):
    _name = 'visitor.type'
    _description = 'Visitor type'

    sequence = fields.Integer(string="Sequence")
    name = fields.Char(string='Name', required=True)
