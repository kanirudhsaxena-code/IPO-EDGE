# IPO EDGE V1.0 Framework Invariants

These invariants must remain true for any V1.x implementation unless changed by an explicitly versioned, validated framework release.

1. Only A+ and A++ are actionable.
2. Critical unverified evidence blocks A+/A++.
3. T1/T2 checkpoints are append-only and immutable.
4. Listing outcomes cannot modify earlier pre-listing grades.
5. Missed opportunity threshold is >=20% actual listing gain for a non-A+/A++ T2 grade.
6. GMP is secondary confirmation only.
7. All eligible Mainboard and SME IPOs are tracked internally.
8. Every recommendation must be reproducible from stored evidence and framework version.
9. Learnings cannot modify weights/rules automatically.
10. A learning must be validated on data not used to originate it before adoption.
11. Standard output order is Efficacy -> Missed Opportunities -> Continuous Learnings -> Current Opportunities.
12. Every automated run must write a run_log record.
