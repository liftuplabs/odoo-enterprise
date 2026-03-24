/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useChildRef, useService } from "@web/core/utils/hooks";
import { Component, useRef, onWillUnmount } from "@odoo/owl";

var beep = new Audio('/barcode_capturing_sale_purchase/static/src/audio/beep_scan.mp3');

export class StockBarcodeDialog extends Component {
    async setup() {
        super.setup();
        this.env.dialogData.dismiss = () => this._cancel();
        this.orm = useService('orm');
        this.notificationService = useService("notification");
        this.modalRef = useChildRef();
        this.videoPreviewRef = useRef("videoPreview");
        this.isMounted = true;

        // Stop camera when component is removed
        onWillUnmount(() => {
            this.isMounted = false;
            this._stopVideoStream();
        });

        // Access the user's camera
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            this.stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        } else {
            this.notificationService.add(_t("Camera access is not available"), {
                title: _t("Error"),
                type: "danger",
            });
            this.props.close();
            return;
        }

        // Set up camera preview
        this.videoPreviewRef.el.srcObject = this.stream;
        this.videoPreviewRef.el.play();

        // Initialize barcode scanner
        Quagga.init({
            inputStream: {
                name: "Live",
                type: "LiveStream",
                target: this.videoPreviewRef.el,
                constraints: {
                    width: 640,
                    height: 480,
                    facingMode: "environment"
                }
            },
            decoder: {
                readers: [
                    "code_128_reader",
                    "ean_reader",
                    "ean_8_reader",
                    "upc_reader",
                    "upc_e_reader"
                ]
            }
        }, (err) => {
            if (err) {
                console.error("Quagga init error:", err);
                return;
            }
            Quagga.start();
        });

        // On barcode detected
        Quagga.onDetected((result) => {
            if (!this.isMounted) return;
            const barcode = result.codeResult.code;
            Quagga.offDetected();
            Quagga.stop();
            this.scan_product(barcode);
        });
    }

    // Cancel dialog
    async _cancel() {
        return this.execButton(this.props.cancel);
    }

    // Confirm dialog
    async _dialogConfirm() {
        return this.execButton(this.props.confirm);
    }

    // Scan and verify product
    async scan_product(barcode) {
        if (!this.isMounted) return;

        beep.play();
        Quagga.stop();

        try {
            const data = await this.orm.call("stock.quant", "barcode_search", [barcode]);

            if (!this.isMounted) return;

            if (data === true) {
                try {
                    if (this.notificationService && this.notificationService.add) {
                        this.notificationService.add(
                            _t(`Product with Serial Number "${barcode}" not found in stock.`),
                            {
                                title: _t("Scan Failed"),
                                type: "danger",
                            }
                        );
                    } else {
                        // Smart button fallback
                        alert(`Product with Serial Number "${barcode}" not found in stock.`);
                    }
                } catch (e) {
                    // Absolute fallback if toast fails silently
                    alert(`Product with Serial Number "${barcode}" not found in stock.`);
                }
            } else {
                // ✅ Reload same view with same domain
                const currentController = this.env.services.action.currentController;
                if (currentController && currentController.action) {
                    await this.env.services.action.doAction(currentController.action, {
                        clearBreadcrumbs: false,
                    });
                }
            }
        } catch (error) {
            console.error("Error scanning product:", error);
        }

        this._stopVideoStream();
        this.props.close();
    }



    // Stop camera stream
    _stopVideoStream() {
        if (this.videoPreviewRef.el && this.videoPreviewRef.el.srcObject) {
            const tracks = this.videoPreviewRef.el.srcObject.getTracks();
            tracks.forEach((track) => track.stop());
        }
    }

    // Disable footer buttons while processing
    setButtonsDisabled(disabled) {
        this.isProcess = disabled;
        if (!this.modalRef.el) return;

        for (const button of this.modalRef.el.querySelectorAll(".modal-footer button")) {
            button.disabled = disabled;
        }
    }

    async execButton(callback) {
        if (this.isProcess) return;

        this.setButtonsDisabled(true);
        if (callback) {
            let shouldClose;
            try {
                shouldClose = await callback();
            } catch (e) {
                this.props.close();
                throw e;
            }
            if (shouldClose === false) {
                this.setButtonsDisabled(false);
                return;
            }
        }
        this.props.close();
    }
}

// Template binding and props setup
StockBarcodeDialog.template = "BarcodeDialogStock";
StockBarcodeDialog.components = { Dialog };
StockBarcodeDialog.props = {
    close: Function,
    model: { type: String, optional: true },
    title: {
        validate: (m) => {
            return (
                typeof m === "string" || (typeof m === "object" && typeof m.toString === "function")
            );
        },
        optional: true,
    },
    body: { type: String, optional: true },
    confirm: { type: Function, optional: true },
    confirmLabel: { type: String, optional: true },
    confirmClass: { type: String, optional: true },
    cancel: { type: Function, optional: true },
    cancelLabel: { type: String, optional: true },
};

StockBarcodeDialog.defaultProps = {
    confirmLabel: _t("Ok"),
    cancelLabel: _t("Cancel"),
    confirmClass: "btn-primary",
    title: _t("Scan Barcode"),
};
