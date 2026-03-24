/** @odoo-module */

import { Component, useState } from "@odoo/owl";

export class BarcodeDialog extends Component {
    setup() {
        this.state = useState({ barcode: "" });
    }

    onCreate() {
        this.props.onConfirm(this.state.barcode);
        this.props.close();
    }

    onCancel() {
        this.props.close();
    }
}

BarcodeDialog.template = "repair.BarcodeDialog";
