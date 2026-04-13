from odoo import http
from odoo.http import request

from odoo.exceptions import UserError
# from geopy.distance import geodesic

# class AttendanceController(http.Controller):
#
#     @http.route('/hr_attendance/custom_check_in_out', type='json', auth="user")
#     def custom_check_in_out(self, latitude, longitude):
#         employee = request.env.user.employee_id
#         company = employee.company_id
#
#         allowed_location = (company.allowed_latitude, company.allowed_longitude)
#         current_location = (latitude, longitude)
#         distance = geodesic(current_location, allowed_location).meters
#
#         if distance > company.location_radius:
#             raise UserError("You can't check in outside the allowed company location.")
#
#         return True

class RepairTrackingController(http.Controller):

    @http.route(['/repair/track/<int:repair_id>'], type='http', auth='public', website=True)
    def track_repair_order(self, repair_id, **kwargs):
        repair = request.env['repair.order'].sudo().browse(repair_id)
        if not repair.exists():
            return request.render('repair_history.404_template')
        return request.render('repair_history.repair_tracking_template', {
            'repair': repair
        })