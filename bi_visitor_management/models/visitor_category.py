# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields


class VisitorCategory(models.Model):
    _name = 'visitor.category'
    _description = 'Visitor category'

    sequence = fields.Integer(string="Sequence")
    name = fields.Char(string='Name', required=True)
