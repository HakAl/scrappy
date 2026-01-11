//# hash=3cd4e8a7bdf0cf544e229ebabdbaedcf
//# sourceMappingURL=escape-cancel.spec.js.map

function asyncGeneratorStep(gen, resolve, reject, _next, _throw, key, arg) {
    try {
        var info = gen[key](arg);
        var value = info.value;
    } catch (error) {
        reject(error);
        return;
    }
    if (info.done) {
        resolve(value);
    } else {
        Promise.resolve(value).then(_next, _throw);
    }
}
function _async_to_generator(fn) {
    return function() {
        var self = this, args = arguments;
        return new Promise(function(resolve, reject) {
            var gen = fn.apply(self, args);
            function _next(value) {
                asyncGeneratorStep(gen, resolve, reject, _next, _throw, "next", value);
            }
            function _throw(err) {
                asyncGeneratorStep(gen, resolve, reject, _next, _throw, "throw", err);
            }
            _next(undefined);
        });
    };
}
function _ts_generator(thisArg, body) {
    var f, y, t, _ = {
        label: 0,
        sent: function() {
            if (t[0] & 1) throw t[1];
            return t[1];
        },
        trys: [],
        ops: []
    }, g = Object.create((typeof Iterator === "function" ? Iterator : Object).prototype), d = Object.defineProperty;
    return d(g, "next", {
        value: verb(0)
    }), d(g, "throw", {
        value: verb(1)
    }), d(g, "return", {
        value: verb(2)
    }), typeof Symbol === "function" && d(g, Symbol.iterator, {
        value: function() {
            return this;
        }
    }), g;
    function verb(n) {
        return function(v) {
            return step([
                n,
                v
            ]);
        };
    }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while(g && (g = 0, op[0] && (_ = 0)), _)try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [
                op[0] & 2,
                t.value
            ];
            switch(op[0]){
                case 0:
                case 1:
                    t = op;
                    break;
                case 4:
                    _.label++;
                    return {
                        value: op[1],
                        done: false
                    };
                case 5:
                    _.label++;
                    y = op[1];
                    op = [
                        0
                    ];
                    continue;
                case 7:
                    op = _.ops.pop();
                    _.trys.pop();
                    continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) {
                        _ = 0;
                        continue;
                    }
                    if (op[0] === 3 && (!t || op[1] > t[0] && op[1] < t[3])) {
                        _.label = op[1];
                        break;
                    }
                    if (op[0] === 6 && _.label < t[1]) {
                        _.label = t[1];
                        t = op;
                        break;
                    }
                    if (t && _.label < t[2]) {
                        _.label = t[2];
                        _.ops.push(op);
                        break;
                    }
                    if (t[2]) _.ops.pop();
                    _.trys.pop();
                    continue;
            }
            op = body.call(thisArg, _);
        } catch (e) {
            op = [
                6,
                e
            ];
            y = 0;
        } finally{
            f = t = 0;
        }
        if (op[0] & 5) throw op[1];
        return {
            value: op[0] ? op[1] : void 0,
            done: true
        };
    }
}
import { test, expect } from "@microsoft/tui-test";
/**
 * Tests for escape key cancellation behavior.
 *
 * Bug: scrappy-kzqy - Need to press escape multiple times to cancel agent
 *
 * Root causes investigated:
 * 1. InputCaptureManager.cancel() didn't reset is_capturing (FIXED in scrappy-z719)
 * 2. Sync LLM calls are blocking - no cancellation check during call
 *
 * This test verifies that a single escape press is sufficient to cancel,
 * and that the UI responds appropriately.
 */ // Serial mode - tests run one at a time
test.use({
    program: {
        file: "scrappy"
    },
    env: {
        LANGFUSE_PUBLIC_KEY: "",
        LANGFUSE_SECRET_KEY: ""
    }
});
test.describe("Escape Key Cancellation", function() {
    test("single escape cancels and returns to idle state", function(param) {
        var terminal = param.terminal;
        return _async_to_generator(function() {
            var buffer, currentBuffer;
            return _ts_generator(this, function(_state) {
                switch(_state.label){
                    case 0:
                        // Wait for app to start
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 8000);
                            })
                        ];
                    case 1:
                        _state.sent();
                        // Handle disclaimer
                        buffer = terminal.getViewableBuffer().join("\n");
                        if (!buffer.includes("NOTICE")) return [
                            3,
                            3
                        ];
                        terminal.submit("ok");
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 5000);
                            })
                        ];
                    case 2:
                        _state.sent();
                        _state.label = 3;
                    case 3:
                        // Skip if in wizard
                        currentBuffer = terminal.getViewableBuffer().join("\n");
                        if (currentBuffer.includes("Provider Setup")) {
                            test.skip();
                            return [
                                2
                            ];
                        }
                        // Submit a query that will start the agent
                        terminal.submit("what is 2+2");
                        // Wait a moment for agent to start
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 1000);
                            })
                        ];
                    case 4:
                        _state.sent();
                        // Press escape ONCE to cancel
                        terminal.keyEscape();
                        // Wait for cancellation to take effect
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 2000);
                            })
                        ];
                    case 5:
                        _state.sent();
                        // Should be able to type new input (not stuck)
                        terminal.write("new query");
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 500);
                            })
                        ];
                    case 6:
                        _state.sent();
                        // The text we typed should be visible
                        return [
                            4,
                            expect(terminal.getByText("new query")).toBeVisible()
                        ];
                    case 7:
                        _state.sent();
                        // Clean up with double ctrl+c
                        terminal.keyCtrlC(2);
                        return [
                            2
                        ];
                }
            });
        })();
    });
    test("escape during activity indicator shows idle after cancel", function(param) {
        var terminal = param.terminal;
        return _async_to_generator(function() {
            var buffer, currentBuffer;
            return _ts_generator(this, function(_state) {
                switch(_state.label){
                    case 0:
                        // Wait for app
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 8000);
                            })
                        ];
                    case 1:
                        _state.sent();
                        // Handle disclaimer
                        buffer = terminal.getViewableBuffer().join("\n");
                        if (!buffer.includes("NOTICE")) return [
                            3,
                            3
                        ];
                        terminal.submit("ok");
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 5000);
                            })
                        ];
                    case 2:
                        _state.sent();
                        _state.label = 3;
                    case 3:
                        // Skip if in wizard
                        currentBuffer = terminal.getViewableBuffer().join("\n");
                        if (currentBuffer.includes("Provider Setup")) {
                            test.skip();
                            return [
                                2
                            ];
                        }
                        // Start agent
                        terminal.submit("hello");
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 1500);
                            })
                        ];
                    case 4:
                        _state.sent();
                        // Cancel
                        terminal.keyEscape();
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 1500);
                            })
                        ];
                    case 5:
                        _state.sent();
                        // After cancel, the activity indicator should be hidden
                        // and input should be ready for new commands
                        // We verify by typing - if stuck, this won't appear
                        terminal.write("test after cancel");
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 500);
                            })
                        ];
                    case 6:
                        _state.sent();
                        return [
                            4,
                            expect(terminal.getByText("test after cancel")).toBeVisible()
                        ];
                    case 7:
                        _state.sent();
                        // Clean up
                        terminal.keyCtrlC(2);
                        return [
                            2
                        ];
                }
            });
        })();
    });
    test("escape works during capture mode prompt", function(param) {
        var terminal = param.terminal;
        return _async_to_generator(function() {
            var buffer, currentBuffer;
            return _ts_generator(this, function(_state) {
                switch(_state.label){
                    case 0:
                        // This test verifies the InputCaptureManager.cancel() fix (scrappy-z719)
                        // When in capture mode, escape should cancel and reset state
                        // Wait for app
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 8000);
                            })
                        ];
                    case 1:
                        _state.sent();
                        // Handle disclaimer
                        buffer = terminal.getViewableBuffer().join("\n");
                        if (!buffer.includes("NOTICE")) return [
                            3,
                            3
                        ];
                        terminal.submit("ok");
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 5000);
                            })
                        ];
                    case 2:
                        _state.sent();
                        _state.label = 3;
                    case 3:
                        // Skip if in wizard - we need main screen
                        currentBuffer = terminal.getViewableBuffer().join("\n");
                        if (currentBuffer.includes("Provider Setup")) {
                            test.skip();
                            return [
                                2
                            ];
                        }
                        // Try to trigger a prompt that enters capture mode
                        // (This depends on having an API key configured for the agent to run)
                        terminal.submit("create a file test.txt");
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 2000);
                            })
                        ];
                    case 4:
                        _state.sent();
                        // If we got a confirmation prompt, escape should cancel it
                        // If agent isn't running (no API key), escape should still work
                        terminal.keyEscape();
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 1000);
                            })
                        ];
                    case 5:
                        _state.sent();
                        // Verify we can type (not stuck in capture mode)
                        terminal.write("after escape");
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 500);
                            })
                        ];
                    case 6:
                        _state.sent();
                        return [
                            4,
                            expect(terminal.getByText("after escape")).toBeVisible()
                        ];
                    case 7:
                        _state.sent();
                        // Clean up
                        terminal.keyCtrlC(2);
                        return [
                            2
                        ];
                }
            });
        })();
    });
});
