/** @odoo-module */

import { MainComponent } from "@mrp_mps/components/main";
import { patch } from "@web/core/utils/patch";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";

patch(MainComponent.prototype, {
    _onClickReplenish(ev) {
        // We use the dialog service which is already initialized in the original setup()
        this.dialog.add(ConfirmationDialog, {
            title: _t("Confirm Order"),
            body: _t("Are you sure you want to process this order?"),
            confirm: () => {
                // If the user clicks "Ok", execute the original function
                super._onClickReplenish(ev);
            },
            cancel: () => {
                // Do nothing if cancelled
            },
        });
    }
});
