/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { parseFloatTime } from "@web/views/fields/parsers";
import { useInputField } from "@web/views/fields/input_field_hook";
import { useRecordObserver } from "@web/model/relational_model/utils";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useState, onWillUpdateProps, onWillStart, onWillDestroy } from "@odoo/owl";

// Format duration (minutes as float) into mm:ss
function formatMinutes(value) {
    if (value === false) {
        return "";
    }
    const isNegative = value < 0;
    if (isNegative) {
        value = Math.abs(value);
    }
    let min = Math.floor(value);
    let sec = Math.round((value % 1) * 60);
    sec = `${sec}`.padStart(2, "0");
    min = `${min}`.padStart(2, "0");
    return `${isNegative ? "-" : ""}${min}:${sec}`;
}

// Timer component
export class MrpTimer extends Component {
    static template = "repair_history.MrpTimer2";
    static props = {
        value: { type: Number },
        ongoing: { type: Boolean, optional: true },
    };
    static defaultProps = { ongoing: false };

    setup() {
        this.state = useState({
            duration: this.props.value,
        });
        this.lastDateTime = Date.now();
        this.ongoing = this.props.ongoing;
        onWillStart(() => {
            if (this.ongoing) {
                this._runTimer();
                this._runSleepTimer();
            }
        });
        onWillUpdateProps((nextProps) => {
            const shouldRestart = !this.ongoing && nextProps.ongoing;
            this.ongoing = nextProps.ongoing;
            if (shouldRestart) {
                this.state.duration = nextProps.value;
                this._runTimer();
                this._runSleepTimer();
            }
        });
        onWillDestroy(() => {
            clearTimeout(this.timer);
            clearTimeout(this.sleepTimer);
        });
    }

    get durationFormatted() {
        return formatMinutes(this.state.duration);
    }

    _runTimer() {
        this.timer = setTimeout(() => {
            if (this.ongoing) {
                this.state.duration += 1 / 60;
                this._runTimer();
            }
        }, 1000);
    }

    _runSleepTimer() {
        this.sleepTimer = setTimeout(() => {
            const diff = Date.now() - this.lastDateTime - 10000;
            if (diff > 1000) {
                this.state.duration += diff / (1000 * 60);
            }
            this.lastDateTime = Date.now();
            this._runSleepTimer();
        }, 10000);
    }
}

// Timer Field Wrapper for use in FormView
class MrpTimerField2 extends Component {
    static template = "repair_history.MrpTimerField2";
    static components = { MrpTimer };
    static props = standardFieldProps;

    setup() {
        this.orm = useService("orm");
        this.duration = this.props.record.data[this.props.name];

        useInputField({
            getValue: () => this.durationFormatted,
            refName: "numpadDecimal",
            parse: (v) => parseFloatTime(v),
        });

        useRecordObserver(async (record) => {
            if (record.data.state === "progress") {
                this.duration = await this.orm.call(
                    "mrp.repair",
                    "get_duration",
                    [this.props.record.resId]
                );
            } else {
                this.duration = record.data[this.props.name];
            }
        });

        onWillDestroy(() => {
            clearTimeout(this.timer);
            clearTimeout(this.sleepTimer);
        });
    }

    get durationFormatted() {
        if (
            this.props.record.data[this.props.name] !== this.duration &&
            this.props.record.dirty
        ) {
            this.duration = this.props.record.data[this.props.name];
        }
        return formatMinutes(this.duration);
    }

    get ongoing() {
        return this.props.record.data.is_user_working;
    }

    //  Your custom startTimer function (triggered from a button)
    async startTimer() {
        await this.orm.call("mrp.repair", "button_start", [this.props.record.resId]);
        this.props.record.update({
            is_user_working: true,
            state: "progress",
            date_finished: false,
        });

        this.duration = currentDuration;
    }
}

// Register field + formatter
export const mrpTimerField2 = {
    component: MrpTimerField2,
    supportedTypes: ["float"],
};

registry.category("fields").add("customer_mrp_timer", mrpTimerField2);
registry.category("formatters").add("customer_mrp_timer", formatMinutes);
