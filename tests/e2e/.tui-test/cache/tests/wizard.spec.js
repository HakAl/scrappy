//# hash=22a5b0e27060acac6f3b5cfa2594baed
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
// Run tests sequentially to avoid resource contention
// Serial mode - tests run one at a time
// Run scrappy - no API keys = wizard should appear
test.use({
    program: {
        file: "scrappy"
    },
    env: {
        LANGFUSE_PUBLIC_KEY: "",
        LANGFUSE_SECRET_KEY: ""
    }
});
test("wizard shows disclaimer on first run", function(param) {
    var terminal = param.terminal;
    return _async_to_generator(function() {
        return _ts_generator(this, function(_state) {
            switch(_state.label){
                case 0:
                    // Wait for app to fully render (8s for Docker startup time)
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 8000);
                        })
                    ];
                case 1:
                    _state.sent();
                    // Check for NOTICE in disclaimer
                    return [
                        4,
                        expect(terminal.getByText("NOTICE")).toBeVisible()
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
test("wizard accepts disclaimer and shows provider menu", function(param) {
    var terminal = param.terminal;
    return _async_to_generator(function() {
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
                    // Verify disclaimer visible
                    return [
                        4,
                        expect(terminal.getByText("NOTICE")).toBeVisible()
                    ];
                case 2:
                    _state.sent();
                    // Accept disclaimer - use submit with text (type + enter combined)
                    terminal.submit("ok");
                    // Wait for transition to provider menu
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 5000);
                        })
                    ];
                case 3:
                    _state.sent();
                    // Provider menu should appear
                    return [
                        4,
                        expect(terminal.getByText("Provider Setup")).toBeVisible()
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
test("wizard can quit with q", function(param) {
    var terminal = param.terminal;
    return _async_to_generator(function() {
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
                    // Verify disclaimer
                    return [
                        4,
                        expect(terminal.getByText("NOTICE")).toBeVisible()
                    ];
                case 2:
                    _state.sent();
                    // Accept disclaimer
                    terminal.submit("ok");
                    // Wait for transition to provider menu
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 5000);
                        })
                    ];
                case 3:
                    _state.sent();
                    // Verify provider menu
                    return [
                        4,
                        expect(terminal.getByText("Provider Setup")).toBeVisible()
                    ];
                case 4:
                    _state.sent();
                    // Quit
                    terminal.submit("q");
                    // Wait for exit
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 2000);
                        })
                    ];
                case 5:
                    _state.sent();
                    return [
                        2
                    ];
            }
        });
    })();
});
test("wizard shows invalid input message for gibberish", function(param) {
    var terminal = param.terminal;
    return _async_to_generator(function() {
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
                    // Accept disclaimer
                    terminal.submit("ok");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 5000);
                        })
                    ];
                case 2:
                    _state.sent();
                    // Type invalid input at provider menu
                    terminal.submit("xyz");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 1000);
                        })
                    ];
                case 3:
                    _state.sent();
                    // Should show invalid selection message
                    return [
                        4,
                        expect(terminal.getByText("Invalid selection")).toBeVisible()
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
test("wizard shows provider config when selecting a provider", function(param) {
    var terminal = param.terminal;
    return _async_to_generator(function() {
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
                    // Accept disclaimer
                    terminal.submit("ok");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 5000);
                        })
                    ];
                case 2:
                    _state.sent();
                    // Select first provider (Groq)
                    terminal.submit("1");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 2000);
                        })
                    ];
                case 3:
                    _state.sent();
                    // Should show configuring message and URL
                    return [
                        4,
                        expect(terminal.getByText("Configuring")).toBeVisible()
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
test("wizard cancels key input with q", function(param) {
    var terminal = param.terminal;
    return _async_to_generator(function() {
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
                    // Accept disclaimer
                    terminal.submit("ok");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 5000);
                        })
                    ];
                case 2:
                    _state.sent();
                    // Select first provider
                    terminal.submit("1");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 2000);
                        })
                    ];
                case 3:
                    _state.sent();
                    // Cancel with q
                    terminal.submit("q");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 2000);
                        })
                    ];
                case 4:
                    _state.sent();
                    // Should show cancelled message and return to menu
                    return [
                        4,
                        expect(terminal.getByText("cancelled")).toBeVisible()
                    ];
                case 5:
                    _state.sent();
                    return [
                        2
                    ];
            }
        });
    })();
});
test("wizard rejects invalid API key format", function(param) {
    var terminal = param.terminal;
    return _async_to_generator(function() {
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
                    // Accept disclaimer
                    terminal.submit("ok");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 5000);
                        })
                    ];
                case 2:
                    _state.sent();
                    // Select first provider
                    terminal.submit("1");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 2000);
                        })
                    ];
                case 3:
                    _state.sent();
                    // Enter invalid key (too short)
                    terminal.submit("abc");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 2000);
                        })
                    ];
                case 4:
                    _state.sent();
                    // Should show invalid key message
                    return [
                        4,
                        expect(terminal.getByText("Invalid key")).toBeVisible()
                    ];
                case 5:
                    _state.sent();
                    return [
                        2
                    ];
            }
        });
    })();
});
test("wizard disclaimer rejects invalid input", function(param) {
    var terminal = param.terminal;
    return _async_to_generator(function() {
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
                    // Type something other than ok or q
                    terminal.submit("hello");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 1000);
                        })
                    ];
                case 2:
                    _state.sent();
                    // Should prompt to type ok or q
                    return [
                        4,
                        expect(terminal.getByText("type 'ok'")).toBeVisible()
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
test("wizard can quit from disclaimer with q", function(param) {
    var terminal = param.terminal;
    return _async_to_generator(function() {
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
                    // Verify disclaimer visible
                    return [
                        4,
                        expect(terminal.getByText("NOTICE")).toBeVisible()
                    ];
                case 2:
                    _state.sent();
                    // Quit directly from disclaimer
                    terminal.submit("q");
                    // Wait for exit
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
test("wizard menu shows all providers", function(param) {
    var terminal = param.terminal;
    return _async_to_generator(function() {
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
                    // Accept disclaimer
                    terminal.submit("ok");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 5000);
                        })
                    ];
                case 2:
                    _state.sent();
                    // Menu should show multiple providers
                    return [
                        4,
                        expect(terminal.getByText("Groq")).toBeVisible()
                    ];
                case 3:
                    _state.sent();
                    return [
                        4,
                        expect(terminal.getByText("Cerebras")).toBeVisible()
                    ];
                case 4:
                    _state.sent();
                    return [
                        4,
                        expect(terminal.getByText("Gemini")).toBeVisible()
                    ];
                case 5:
                    _state.sent();
                    return [
                        2
                    ];
            }
        });
    })();
});
test("wizard shows console URL when configuring provider", function(param) {
    var terminal = param.terminal;
    return _async_to_generator(function() {
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
                    // Accept disclaimer
                    terminal.submit("ok");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 5000);
                        })
                    ];
                case 2:
                    _state.sent();
                    // Select first provider
                    terminal.submit("1");
                    return [
                        4,
                        new Promise(function(r) {
                            return setTimeout(r, 2000);
                        })
                    ];
                case 3:
                    _state.sent();
                    // Should show console URL for getting API key
                    return [
                        4,
                        expect(terminal.getByText("console.groq.com")).toBeVisible()
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
