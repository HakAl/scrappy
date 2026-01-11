//# hash=17b8cc7be0100c7e0aa41c6f09315bd1
//# sourceMappingURL=cancel.spec.js.map

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
 * Tests for cancellation behavior and post-cancel input handling.
 *
 * Bug: scrappy-z719 - Arrow keys don't work after agent cancel
 * Root cause: InputCaptureManager.cancel() doesn't reset _mode flag,
 * so is_capturing stays True and blocks history navigation.
 */ // Run tests sequentially to avoid resource contention
// Serial mode - tests run one at a time
// Configure scrappy with no tracing
test.use({
    program: {
        file: "scrappy"
    },
    env: {
        LANGFUSE_PUBLIC_KEY: "",
        LANGFUSE_SECRET_KEY: ""
    }
});
test.describe("Cancellation and Arrow Keys", function() {
    test("arrow keys work for history after cancel during prompt", function(param) {
        var terminal = param.terminal;
        return _async_to_generator(function() {
            var buffer, currentBuffer;
            return _ts_generator(this, function(_state) {
                switch(_state.label){
                    case 0:
                        // Wait for app to fully render
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 8000);
                            })
                        ];
                    case 1:
                        _state.sent();
                        // Accept disclaimer if it appears
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
                        // Skip if we're in wizard (no API keys configured)
                        currentBuffer = terminal.getViewableBuffer().join("\n");
                        if (currentBuffer.includes("Provider Setup")) {
                            test.skip();
                            return [
                                2
                            ];
                        }
                        // Type and submit a command to add to history
                        terminal.submit("hello");
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 2000);
                            })
                        ];
                    case 4:
                        _state.sent();
                        // If agent started (shows thinking indicator), cancel with escape
                        terminal.keyEscape();
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 1000);
                            })
                        ];
                    case 5:
                        _state.sent();
                        // Type another command
                        terminal.submit("world");
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 2000);
                            })
                        ];
                    case 6:
                        _state.sent();
                        // Cancel again if needed
                        terminal.keyEscape();
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 1000);
                            })
                        ];
                    case 7:
                        _state.sent();
                        // Now test arrow key history navigation
                        // Up arrow should bring back "world" from history
                        terminal.keyUp();
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 500);
                            })
                        ];
                    case 8:
                        _state.sent();
                        // The input should now contain "world"
                        return [
                            4,
                            expect(terminal.getByText("world")).toBeVisible()
                        ];
                    case 9:
                        _state.sent();
                        // Up arrow again should bring back "hello"
                        terminal.keyUp();
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 500);
                            })
                        ];
                    case 10:
                        _state.sent();
                        return [
                            4,
                            expect(terminal.getByText("hello")).toBeVisible()
                        ];
                    case 11:
                        _state.sent();
                        return [
                            2
                        ];
                }
            });
        })();
    });
    test("escape key cancels and returns to idle state", function(param) {
        var terminal = param.terminal;
        return _async_to_generator(function() {
            var buffer, currentBuffer;
            return _ts_generator(this, function(_state) {
                switch(_state.label){
                    case 0:
                        // Wait for app to fully render
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 8000);
                            })
                        ];
                    case 1:
                        _state.sent();
                        // Accept disclaimer if it appears
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
                        // Type a command to potentially start an agent
                        terminal.submit("test");
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 1000);
                            })
                        ];
                    case 4:
                        _state.sent();
                        // Press escape to cancel
                        terminal.keyEscape();
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 1000);
                            })
                        ];
                    case 5:
                        _state.sent();
                        // Should be able to type new input (not stuck)
                        terminal.write("new input");
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
                            expect(terminal.getByText("new input")).toBeVisible()
                        ];
                    case 7:
                        _state.sent();
                        return [
                            2
                        ];
                }
            });
        })();
    });
    test("ctrl+c double tap exits cleanly", function(param) {
        var terminal = param.terminal;
        return _async_to_generator(function() {
            return _ts_generator(this, function(_state) {
                switch(_state.label){
                    case 0:
                        // Wait for app to start
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 3000);
                            })
                        ];
                    case 1:
                        _state.sent();
                        // Double ctrl+c should exit
                        terminal.keyCtrlC(2);
                        // Give time for clean exit
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 1000);
                            })
                        ];
                    case 2:
                        _state.sent();
                        return [
                            2
                        ];
                }
            });
        })();
    });
});
