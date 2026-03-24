/** @odoo-module */

import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { useService } from "@web/core/utils/hooks";
import { BarcodeDialog } from "./barcode_dialog";

export class RepairBarcodeListController extends ListController {
    setup() {
        super.setup();
        this.dialogService = useService("dialog");
    }

    async onScanBarcodeClick() {
        await this.dialogService.add(BarcodeDialog, {
            onConfirm: async (barcode) => {
                if (barcode) {
                    await this.rpc({
                        model: "repair.order",
                        method: "create_repair_order_from_barcode",
                        args: [barcode],
                    });
                    this.model.load(); // reload list
                }
            },
        });
    }
}

RepairBarcodeListController.template = "repair.ListView.Buttons";

export const RepairBarcodeListView = {
    ...listView,
    Controller: RepairBarcodeListController,
};

registry.category("views").add("repair_barcode_list", RepairBarcodeListView);
