//===----------------------------------------------------------------------===//
//                                                                            //
//    ______    _                                                             //
//   /_  __/___(_)_  __                                                       //
//    / / / __/ /\ \/ /       Stack-Based Interpreter & VM                    //
//   / / / / / /  > · <      C++23 · Single-Header Library                    //
//  /_/ /_/ /_/  /_/\_\     Copyright 2026 Mark Guidarelli                    //
//                                                                            //
// Licensed under the Apache License, Version 2.0 (the "License");            //
// you may not use this file except in compliance with the License.           //
// You may obtain a copy of the License at                                    //
//                                                                            //
//     https://www.apache.org/licenses/LICENSE-2.0                            //
//                                                                            //
// Unless required by applicable law or agreed to in writing, software        //
// distributed under the License is distributed on an "AS IS" BASIS,          //
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.   //
// See the License for the specific language governing permissions and        //
// limitations under the License.                                             //
//                                                                            //
//===----------------------------------------------------------------------===//
private:
//===--- Scan-Time Stack-Effect Checker ---===//
//
// When a procedure declares a stack effect with the `|params -- outputs|`
// preamble form, the scanner abstractly interprets the packed body once (at
// scan time, zero run-time cost) and verifies that the body actually leaves
// `outputs` values on the operand stack, consuming no more than its declared
// `params`.  Best-effort and sound: it only reports a violation it can PROVE,
// and silently accepts (bails) anything it cannot fully analyze, so it never
// false-positives.
//
// The abstract operand stack tracks a depth plus, per slot, whether the slot
// holds a nested {proc} literal and that proc's own net effect -- the latter
// lets the combinators if / if-else / repeat reason about their branches.
//
// Bails (accepted without a verdict): variadic / unknown-arity operators (see
// the generated arity table in op_effects.inl), executable names that resolve
// to a user proc or are unresolved at scan time, a {proc} branch whose net
// effect is itself unknown, dynamic name lookup, and abstract stacks deeper
// than MaxStackEffectStack.  A nested {proc} literal that is pushed (not
// directly executed by a combinator) degrades any internal imbalance to
// "unknown net" rather than reporting it -- the proc may never run.

static constexpr int MaxStackEffectStack{64};  // abstract operand-stack cap; deeper => bail

// SystemName-indexed view of the generated arity rows (op_effects.inl).  Built
// once, the same way build_sysoperator_table() builds the dispatch table.
[[nodiscard]] static consteval std::array<OpEffect, SYSOPERATOR_COUNT> build_op_effect_table() {
    std::array<OpEffect, SYSOPERATOR_COUNT> table{};  // every entry defaults to {0, 0, false}
    for (auto row : sm_op_effect_rows) {
        table[static_cast<size_t>(+row.m_name) - SYSVARIABLE_COUNT] = OpEffect{row.m_in, row.m_out, true};
    }
    return table;
}

// Fixed arity of a system operator, or {0, 0, false} for variables, internal
// ops, or any operator the checker must not trust statically.
[[nodiscard]] static OpEffect op_effect_for(SystemName sysname) {
    static constexpr auto sm_op_effects{build_op_effect_table()};
    auto index = +sysname;
    if ((index < SYSVARIABLE_COUNT) || (index >= SYSTEMNAME_COUNT)) {
        return OpEffect{};
    } else {
        return sm_op_effects[static_cast<size_t>(index) - SYSVARIABLE_COUNT];
    }
}

// Outcome of abstractly interpreting a proc body.
//   Ok        -- net is the known stack delta; min_depth is the lowest depth
//                reached relative to the start (negative => drew below the start).
//   Bail      -- the body used something unanalyzable; accept with no verdict.
//   Imbalance -- a definite contradiction (an executed if/repeat branch is not
//                stack-neutral, or if-else branches disagree).
enum struct StackEffectKind { Ok, Bail, Imbalance };
struct ProcEffect {
    StackEffectKind kind{StackEffectKind::Bail};
    int net{0};
    int min_depth{0};
};

// One abstract operand-stack slot.  proc slots carry the nested {proc}'s net
// effect so a following combinator can reason about its branch.
struct StackSlot {
    bool is_proc{false};
    bool proc_known{false};
    int proc_net{0};
};

// Abstractly interpret one proc body (packed or array) and report its effect.
// Recurses into nested {proc} literals.  Reads VM storage only; never mutates.
[[nodiscard]] ProcEffect analyze_proc(Trix *trx, Object proc_obj) {
    StackSlot slots[MaxStackEffectStack]{};
    auto depth = 0;
    auto min_depth = 0;
    auto overflowed = false;

    auto pop_value = [&]() {
        --depth;
        if (depth < min_depth) {
            min_depth = depth;
        }
    };
    // depth may be negative while a body draws below its own start (a combinator
    // branch consuming parent-stack values); slots only exist for indices >= 0, and
    // those in [0, depth) are always freshly written, so combinators read valid data.
    auto push_value = [&]() {
        if (depth >= MaxStackEffectStack) {
            overflowed = true;
        } else {
            if (depth >= 0) {
                slots[depth] = StackSlot{false, false, 0};
            }
            ++depth;
        }
    };
    auto push_proc = [&](bool known, int net) {
        if (depth >= MaxStackEffectStack) {
            overflowed = true;
        } else {
            if (depth >= 0) {
                slots[depth] = StackSlot{true, known, net};
            }
            ++depth;
        }
    };

    // Apply one resolved operator to the abstract stack.
    auto apply_operator = [&](operator_index_t op_index) -> StackEffectKind {
        if (op_index < 0) {
            return StackEffectKind::Bail;  // user-registered C operator: unknown arity
        } else {
            auto sysname = static_cast<SystemName>(op_index);
            if ((sysname == SystemName::If) || (sysname == SystemName::Repeat)) {
                // `cond {body} if` / `count {body} repeat`: the body runs zero or
                // more times, so for a fixed effect it must be stack-neutral.
                if ((depth >= 1) && slots[depth - 1].is_proc) {
                    if (!slots[depth - 1].proc_known) {
                        return StackEffectKind::Bail;
                    } else if (slots[depth - 1].proc_net != 0) {
                        return StackEffectKind::Imbalance;
                    } else {
                        pop_value();  // body proc
                        pop_value();  // cond / count
                        return StackEffectKind::Ok;
                    }
                } else {
                    return StackEffectKind::Bail;  // body proc not statically present
                }
            } else if (sysname == SystemName::IfElse) {
                // `cond {then} {else} if-else`: both branches must agree on net.
                if ((depth >= 2) && slots[depth - 1].is_proc && slots[depth - 2].is_proc) {
                    if ((!slots[depth - 1].proc_known) || (!slots[depth - 2].proc_known)) {
                        return StackEffectKind::Bail;
                    } else if (slots[depth - 1].proc_net != slots[depth - 2].proc_net) {
                        return StackEffectKind::Imbalance;
                    } else {
                        auto branch_net = slots[depth - 1].proc_net;
                        pop_value();  // else proc
                        pop_value();  // then proc
                        pop_value();  // cond
                        if (branch_net >= 0) {
                            for (int i = 0; i < branch_net; ++i) {
                                push_value();
                            }
                        } else {
                            for (int i = 0; i < (-branch_net); ++i) {
                                pop_value();
                            }
                        }
                        return StackEffectKind::Ok;
                    }
                } else {
                    return StackEffectKind::Bail;
                }
            } else {
                auto eff = op_effect_for(sysname);
                if (!eff.known) {
                    return StackEffectKind::Bail;
                } else {
                    for (int i = 0; i < static_cast<int>(eff.in); ++i) {
                        pop_value();
                    }
                    for (int i = 0; i < static_cast<int>(eff.out); ++i) {
                        push_value();
                    }
                    return StackEffectKind::Ok;
                }
            }
        }
    };

    // Apply one body element to the abstract stack.
    auto handle = [&](Object elem_obj) -> StackEffectKind {
        if (elem_obj.is_slot_ref()) {
            push_value();  // frame-slot read pushes one value
            return StackEffectKind::Ok;
        } else if (elem_obj.is_operator()) {
            return apply_operator(elem_obj.m_operator);
        } else if (elem_obj.is_name() && elem_obj.is_executable()) {
            auto bound_ptr = Name::name_search(trx, elem_obj);
            if (bound_ptr == nullptr) {
                return StackEffectKind::Bail;  // unresolved now; may bind at run time
            } else if (bound_ptr->is_operator()) {
                return apply_operator(bound_ptr->m_operator);
            } else if (bound_ptr->is_executable()) {
                return StackEffectKind::Bail;  // user proc / exec-name: unknown effect
            } else {
                push_value();  // name bound to a constant value pushes it
                return StackEffectKind::Ok;
            }
        } else if (elem_obj.is_executable() && (elem_obj.is_packed() || elem_obj.is_array())) {
            auto child = analyze_proc(trx, elem_obj);  // nested {proc} literal: pushed, not run
            push_proc((child.kind == StackEffectKind::Ok), child.net);
            return StackEffectKind::Ok;
        } else {
            push_value();  // literal value (number / string / bool / null / mark / literal-name)
            return StackEffectKind::Ok;
        }
    };

    auto status = StackEffectKind::Ok;
    if (proc_obj.is_packed()) {
        if (proc_obj.m_arrays_length != 0) {
            auto [data_ptr, count] = proc_obj.packed_value(trx);
            const auto *cursor = data_ptr;
            auto remaining = count;
            while (true) {
                if ((remaining == 0) || (status != StackEffectKind::Ok) || overflowed) {
                    break;
                } else {
                    auto [next, elem_obj] = Object::extract_next_packed(trx, cursor);
                    status = handle(elem_obj);
                    cursor = next;
                    --remaining;
                }
            }
        }
    } else if (proc_obj.is_array()) {
        auto [elem_data, length] = proc_obj.array_value(trx);
        for (length_t i = 0; (i < length) && (status == StackEffectKind::Ok) && !overflowed; ++i) {
            status = handle(elem_data[i]);
        }
    } else {
        status = StackEffectKind::Bail;
    }

    if (overflowed || (status == StackEffectKind::Bail)) {
        return ProcEffect{StackEffectKind::Bail, 0, 0};
    } else if (status == StackEffectKind::Imbalance) {
        return ProcEffect{StackEffectKind::Imbalance, 0, 0};
    } else {
        return ProcEffect{StackEffectKind::Ok, depth, min_depth};
    }
}

// Verdict of checking a declared-effect proc body against its output count.
enum struct StackEffectResult { Ok, Imbalance, Underflow, Mismatch };
struct StackEffectVerdict {
    StackEffectResult result{StackEffectResult::Ok};
    int net{0};
    int underflow{0};
};

// Check a `|params -- outputs|` proc body (the inner packed body) against its
// declared output count.  Returns Ok for both "conforms" and "unanalyzable".
[[nodiscard]] StackEffectVerdict check_stack_effect(Trix *trx, Object body_proc_obj, length_t out_count) {
    auto eff = analyze_proc(trx, body_proc_obj);
    if (eff.kind == StackEffectKind::Bail) {
        return StackEffectVerdict{StackEffectResult::Ok, 0, 0};
    } else if (eff.kind == StackEffectKind::Imbalance) {
        return StackEffectVerdict{StackEffectResult::Imbalance, 0, 0};
    } else if (eff.min_depth < 0) {
        return StackEffectVerdict{StackEffectResult::Underflow, eff.net, -eff.min_depth};
    } else if (eff.net != static_cast<int>(out_count)) {
        return StackEffectVerdict{StackEffectResult::Mismatch, eff.net, 0};
    } else {
        return StackEffectVerdict{StackEffectResult::Ok, eff.net, 0};
    }
}

// Restore the enclosing-class access to public for the following includes
// (stream.inl / save.inl define classes that inherit the ambient specifier).
public:
