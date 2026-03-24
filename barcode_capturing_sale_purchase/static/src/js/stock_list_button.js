/** @odoo-module */

import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { useService } from "@web/core/utils/hooks";
import { StockBarcodeDialog } from "./barcode_stock_dialog";

export class StockBarcodeListController extends ListController {
    setup() {
        super.setup();
        this.dialogService = useService("dialog");
    }

    async onScanBarcodeClick2() {
        await this.dialogService.add(StockBarcodeDialog, {
            onConfirm: async (barcode) => {
                if (barcode) {
                    await this.rpc({
                        model: "stock.quant",
                        method: "_check_stock_avail",
                        args: [barcode],
                    });
                    this.model.load(); // reload list
                }
            },
        });
    }

    onScanBarcodeClick3() {
       this.actionService.doAction({
          type: 'ir.actions.act_window',
          name: 'Verify Barcode',
           res_model: 'verify.barcode.wizard',
          view_mode: 'form',
          view_type: 'form',
          views: [[false, 'form']],
          target: 'new',
          res_id: false,
      });
   }

    /** Inside your OWL Component method */

}

StockBarcodeListController.template = "stock.ListView.Buttons";

export const StockBarcodeListView = {
    ...listView,
    Controller: StockBarcodeListController,
};

registry.category("views").add("stock_barcode_list", StockBarcodeListView);
