/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { onWillStart, useState, onWillUnmount } from "@odoo/owl";

patch(ControlPanel.prototype, {
    setup() {
        super.setup();
        if (!this.env.searchModel) return;

        this.dateFilterState = useState({
            config: null,
            fieldName: null,
            fromDate: "",
            toDate: "",
            isOpen: false
        });

        this._onOutsideClick = this._onOutsideClick.bind(this);

        onWillStart(async () => {
            if (!this.env.searchModel) return;
            const configs = await this.env.services.orm.searchRead(
                "date.filter.config",
                [["model_name", "=", this.env.searchModel.resModel], ["active", "=", true]],
                ["date_field_id"]
            );
            if (configs.length > 0) {
                this.dateFilterState.config = configs[0];
                const fieldInfo = await this.env.services.orm.searchRead(
                    "ir.model.fields",
                    [["id", "=", configs[0].date_field_id[0]]],
                    ["name"]
                );
                if(fieldInfo.length > 0) this.dateFilterState.fieldName = fieldInfo[0].name;
            }
        });

        onWillUnmount(() => {
            document.removeEventListener('click', this._onOutsideClick);
        });
    },

    // Helper to format YYYY-MM-DD to DD/MM/YYYY
    formatDisplayDate(dateStr) {
        if (!dateStr) return "";
        const [y, m, d] = dateStr.split("-");
        return `${d}/${m}/${y}`;
    },

    _onOutsideClick(ev) {
        if (!ev.target.closest('.o_date_range_filter')) {
            this.dateFilterState.isOpen = false;
            document.removeEventListener('click', this._onOutsideClick);
        }
    },

    toggleDateDropdown() {
        if (!this.env.searchModel) return;
        this.dateFilterState.isOpen = !this.dateFilterState.isOpen;
        if (this.dateFilterState.isOpen) {
            setTimeout(() => document.addEventListener('click', this._onOutsideClick), 0);
        } else {
            document.removeEventListener('click', this._onOutsideClick);
        }
    },

    applyCustomDateRange() {
        if (!this.env.searchModel || !this.dateFilterState.fromDate || !this.dateFilterState.toDate) return;

        const field = this.dateFilterState.fieldName;
        // Domain requires YYYY-MM-DD format
        const domain = [
            [field, '>=', this.dateFilterState.fromDate + " 00:00:00"],
            [field, '<=', this.dateFilterState.toDate + " 23:59:59"]
        ];

        this.dateFilterState.isOpen = false;
        document.removeEventListener('click', this._onOutsideClick);

        // Use the new helper for the description
        const desc = `Custom: ${this.formatDisplayDate(this.dateFilterState.fromDate)} to ${this.formatDisplayDate(this.dateFilterState.toDate)}`;
        this._applyDomainToSearchModel(domain, desc);
    },

    _applyDomainToSearchModel(domain, description) {
        if (!this.env.searchModel) return;
        const searchModel = this.env.searchModel;

        const existingFilters = searchModel.getSearchItems((item) => item.isCustomDateFilter);
        for (const filter of existingFilters) {
            if (filter.isActive) searchModel.toggleSearchItem(filter.id);
        }

        if (domain && domain.length > 0) {
            searchModel.createNewFilters([{
                description: description,
                domain: domain,
                isCustomDateFilter: true
            }]);
        }
    }
});