pragma circom 2.0.0;

include "../node_modules/circomlib/circuits/comparators.circom";

template RiskGate() {
    signal input privateRiskScore;   // AI output (hidden)
    signal input publicThreshold;    // protocol limit

    signal output allowed;

    component geq = GreaterEqThan(64);
    geq.in[0] <== privateRiskScore;
    geq.in[1] <== publicThreshold;

    allowed <== geq.out;
}

component main {public [publicThreshold]} = RiskGate();