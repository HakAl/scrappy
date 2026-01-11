//# hash=d5bd7a59c53dbf0c0a9c77909cc177d5
//# sourceMappingURL=wizard.spec.js.map

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
// No API keys = wizard should appear
test.use({
    env: {
        LANGFUSE_PUBLIC_KEY: "",
        LANGFUSE_SECRET_KEY: ""
    }
});
test.describe("Setup Wizard", function() {
    test("shows disclaimer on first run", function(param) {
        var terminal = param.terminal;
        return _async_to_generator(function() {
            return _ts_generator(this, function(_state) {
                switch(_state.label){
                    case 0:
                        // Wizard should show disclaimer panel
                        return [
                            4,
                            expect(terminal.getByText("Terms of Use", {
                                timeout: 10000
                            })).toBeVisible()
                        ];
                    case 1:
                        _state.sent();
                        // Disclaimer content should be visible
                        return [
                            4,
                            expect(terminal.getByText("NOTICE", {
                                timeout: 5000
                            })).toBeVisible()
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
    test("accepts disclaimer and shows provider menu", function(param) {
        var terminal = param.terminal;
        return _async_to_generator(function() {
            return _ts_generator(this, function(_state) {
                switch(_state.label){
                    case 0:
                        // Wait for disclaimer
                        return [
                            4,
                            expect(terminal.getByText("Terms of Use", {
                                timeout: 10000
                            })).toBeVisible()
                        ];
                    case 1:
                        _state.sent();
                        // Accept disclaimer
                        terminal.write("ok");
                        terminal.submit();
                        // Provider menu should appear
                        return [
                            4,
                            expect(terminal.getByText("Provider Setup", {
                                timeout: 5000
                            })).toBeVisible()
                        ];
                    case 2:
                        _state.sent();
                        // Should show provider options
                        return [
                            4,
                            expect(terminal.getByText("Groq", {
                                timeout: 3000
                            })).toBeVisible()
                        ];
                    case 3:
                        _state.sent();
                        return [
                            2
                        ];
                }
            });
        })();
    });
    test("can quit wizard with q", function(param) {
        var terminal = param.terminal;
        return _async_to_generator(function() {
            return _ts_generator(this, function(_state) {
                switch(_state.label){
                    case 0:
                        // Wait for disclaimer
                        return [
                            4,
                            expect(terminal.getByText("Terms of Use", {
                                timeout: 10000
                            })).toBeVisible()
                        ];
                    case 1:
                        _state.sent();
                        // Accept disclaimer
                        terminal.write("ok");
                        terminal.submit();
                        // Wait for provider menu
                        return [
                            4,
                            expect(terminal.getByText("Provider Setup", {
                                timeout: 5000
                            })).toBeVisible()
                        ];
                    case 2:
                        _state.sent();
                        // Quit wizard
                        terminal.write("q");
                        terminal.submit();
                        // Should exit to main screen or exit app
                        // Give time for transition
                        return [
                            4,
                            new Promise(function(r) {
                                return setTimeout(r, 2000);
                            })
                        ];
                    case 3:
                        _state.sent();
                        return [
                            2
                        ];
                }
            });
        })();
    });
    test("can select provider and cancel", function(param) {
        var terminal = param.terminal;
        return _async_to_generator(function() {
            return _ts_generator(this, function(_state) {
                switch(_state.label){
                    case 0:
                        // Wait for disclaimer
                        return [
                            4,
                            expect(terminal.getByText("Terms of Use", {
                                timeout: 10000
                            })).toBeVisible()
                        ];
                    case 1:
                        _state.sent();
                        // Accept disclaimer
                        terminal.write("ok");
                        terminal.submit();
                        // Wait for provider menu
                        return [
                            4,
                            expect(terminal.getByText("Provider Setup", {
                                timeout: 5000
                            })).toBeVisible()
                        ];
                    case 2:
                        _state.sent();
                        // Select first provider (Groq)
                        terminal.write("1");
                        terminal.submit();
                        // Should show configuration prompt
                        return [
                            4,
                            expect(terminal.getByText("Configuring", {
                                timeout: 5000
                            })).toBeVisible()
                        ];
                    case 3:
                        _state.sent();
                        // Cancel with q
                        terminal.write("q");
                        terminal.submit();
                        // Should return to menu
                        return [
                            4,
                            expect(terminal.getByText("Provider Setup", {
                                timeout: 5000
                            })).toBeVisible()
                        ];
                    case 4:
                        _state.sent();
                        return [
                            2
                        ];
                }
            });
        })();
    });
});
