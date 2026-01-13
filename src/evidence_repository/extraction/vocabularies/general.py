"""General vocabulary for cross-domain extraction."""

from evidence_repository.extraction.vocabularies.base import (
    BaseVocabulary,
    ClaimPredicate,
    MetricDefinition,
    RiskCategory,
)


class GeneralVocabulary(BaseVocabulary):
    """General-purpose vocabulary for cross-domain extraction.

    Provides baseline metrics, claims, and risks applicable to
    any document type.
    """

    @property
    def profile_code(self) -> str:
        return "general"

    @property
    def profile_name(self) -> str:
        return "General"

    def get_metrics(self, level: int = 1) -> list[MetricDefinition]:
        """Get general metrics by extraction level."""
        all_metrics = [
            # L1: Basic financial metrics
            MetricDefinition(
                name="revenue",
                display_name="Revenue",
                description="Total revenue or sales",
                unit_type="currency",
                aliases=["sales", "total_revenue", "net_revenue", "gross_revenue"],
                required_level=1,
            ),
            MetricDefinition(
                name="profit",
                display_name="Profit",
                description="Net profit or net income",
                unit_type="currency",
                aliases=["net_income", "net_profit", "earnings", "bottom_line"],
                required_level=1,
            ),
            MetricDefinition(
                name="headcount",
                display_name="Headcount",
                description="Total number of employees",
                unit_type="count",
                aliases=["employees", "staff_count", "workforce", "fte"],
                required_level=1,
            ),
            # L2: Extended financial metrics
            MetricDefinition(
                name="gross_margin",
                display_name="Gross Margin",
                description="Gross profit as percentage of revenue",
                unit_type="percentage",
                aliases=["gm", "gross_profit_margin"],
                required_level=2,
            ),
            MetricDefinition(
                name="operating_margin",
                display_name="Operating Margin",
                description="Operating income as percentage of revenue",
                unit_type="percentage",
                aliases=["op_margin", "operating_profit_margin"],
                required_level=2,
            ),
            MetricDefinition(
                name="ebitda",
                display_name="EBITDA",
                description="Earnings before interest, taxes, depreciation, and amortization",
                unit_type="currency",
                aliases=["adjusted_ebitda"],
                required_level=2,
            ),
            MetricDefinition(
                name="cash",
                display_name="Cash",
                description="Cash and cash equivalents",
                unit_type="currency",
                aliases=["cash_on_hand", "cash_balance", "cash_position"],
                required_level=2,
            ),
            # L3: Detailed metrics
            MetricDefinition(
                name="debt",
                display_name="Total Debt",
                description="Total debt obligations",
                unit_type="currency",
                aliases=["total_debt", "debt_balance", "outstanding_debt"],
                required_level=3,
            ),
            MetricDefinition(
                name="assets",
                display_name="Total Assets",
                description="Total assets on balance sheet",
                unit_type="currency",
                aliases=["total_assets"],
                required_level=3,
            ),
            MetricDefinition(
                name="liabilities",
                display_name="Total Liabilities",
                description="Total liabilities on balance sheet",
                unit_type="currency",
                aliases=["total_liabilities"],
                required_level=3,
            ),
            MetricDefinition(
                name="equity",
                display_name="Shareholders' Equity",
                description="Total shareholders' equity",
                unit_type="currency",
                aliases=["shareholders_equity", "book_value", "net_assets"],
                required_level=3,
            ),
            # L4: Forensic-level metrics
            MetricDefinition(
                name="working_capital",
                display_name="Working Capital",
                description="Current assets minus current liabilities",
                unit_type="currency",
                aliases=["net_working_capital"],
                required_level=4,
            ),
            MetricDefinition(
                name="capex",
                display_name="Capital Expenditure",
                description="Capital expenditure",
                unit_type="currency",
                aliases=["capital_expenditure", "pp&e_additions"],
                required_level=4,
            ),
        ]
        return [m for m in all_metrics if m.required_level <= level]

    def get_claim_predicates(self, level: int = 1) -> list[ClaimPredicate]:
        """Get general claim predicates by extraction level."""
        all_predicates = [
            # L1: Basic claims
            ClaimPredicate(
                name="has_certification",
                display_name="Has Certification",
                description="Entity holds a certification",
                subject_types=["company", "organization", "product"],
                object_types=["certification"],
                required_level=1,
            ),
            ClaimPredicate(
                name="is_compliant_with",
                display_name="Is Compliant With",
                description="Entity is compliant with regulation/standard",
                subject_types=["company", "organization", "product", "process"],
                object_types=["regulation", "standard", "framework"],
                required_level=1,
            ),
            ClaimPredicate(
                name="operates_in",
                display_name="Operates In",
                description="Entity operates in region/market",
                subject_types=["company", "organization"],
                object_types=["region", "market", "jurisdiction"],
                required_level=1,
            ),
            # L2: Extended claims
            ClaimPredicate(
                name="has_policy",
                display_name="Has Policy",
                description="Entity has a specific policy in place",
                subject_types=["company", "organization"],
                object_types=["policy"],
                required_level=2,
            ),
            ClaimPredicate(
                name="underwent_audit",
                display_name="Underwent Audit",
                description="Entity underwent audit",
                subject_types=["company", "organization", "process"],
                object_types=["audit_type"],
                required_level=2,
            ),
            ClaimPredicate(
                name="has_contract_with",
                display_name="Has Contract With",
                description="Entity has contractual relationship",
                subject_types=["company", "organization"],
                object_types=["company", "organization"],
                required_level=2,
            ),
            # L3: Detailed claims
            ClaimPredicate(
                name="owns_ip",
                display_name="Owns IP",
                description="Entity owns intellectual property",
                subject_types=["company", "organization", "person"],
                object_types=["patent", "trademark", "copyright", "trade_secret"],
                required_level=3,
            ),
            ClaimPredicate(
                name="has_liability",
                display_name="Has Liability",
                description="Entity has legal/financial liability",
                subject_types=["company", "organization"],
                object_types=["liability_type"],
                required_level=3,
            ),
            ClaimPredicate(
                name="experienced_incident",
                display_name="Experienced Incident",
                description="Entity experienced security/operational incident",
                subject_types=["company", "organization"],
                object_types=["incident_type"],
                required_level=3,
            ),
            # L4: Forensic claims
            ClaimPredicate(
                name="related_party_transaction",
                display_name="Related Party Transaction",
                description="Entity engaged in related party transaction",
                subject_types=["company", "organization", "person"],
                object_types=["transaction"],
                required_level=4,
            ),
            ClaimPredicate(
                name="has_contingency",
                display_name="Has Contingency",
                description="Entity has contingent liability/asset",
                subject_types=["company", "organization"],
                object_types=["contingency"],
                required_level=4,
            ),
        ]
        return [p for p in all_predicates if p.required_level <= level]

    def get_risk_categories(self, level: int = 2) -> list[RiskCategory]:
        """Get general risk categories by extraction level."""
        if level < 2:
            return []

        all_risks = [
            # L2: Standard risks
            RiskCategory(
                name="financial_risk",
                display_name="Financial Risk",
                description="Risks related to financial position or performance",
                indicators=["declining revenue", "cash burn", "debt covenants", "liquidity concerns"],
                required_level=2,
            ),
            RiskCategory(
                name="compliance_risk",
                display_name="Compliance Risk",
                description="Risks related to regulatory compliance",
                indicators=["regulatory violations", "audit findings", "pending investigations"],
                required_level=2,
            ),
            RiskCategory(
                name="operational_risk",
                display_name="Operational Risk",
                description="Risks related to business operations",
                indicators=["supply chain issues", "key person dependency", "system failures"],
                required_level=2,
            ),
            # L3: Detailed risks
            RiskCategory(
                name="legal_risk",
                display_name="Legal Risk",
                description="Risks from litigation or legal issues",
                indicators=["pending lawsuits", "regulatory actions", "contract disputes"],
                required_level=3,
            ),
            RiskCategory(
                name="reputational_risk",
                display_name="Reputational Risk",
                description="Risks to reputation or brand",
                indicators=["negative press", "customer complaints", "executive misconduct"],
                required_level=3,
            ),
            RiskCategory(
                name="cyber_risk",
                display_name="Cyber Risk",
                description="Risks from cybersecurity threats",
                indicators=["data breaches", "ransomware", "system vulnerabilities"],
                required_level=3,
            ),
            # L4: Forensic risks
            RiskCategory(
                name="fraud_risk",
                display_name="Fraud Risk",
                description="Risks from fraudulent activity",
                indicators=["accounting irregularities", "unusual transactions", "whistleblower reports"],
                required_level=4,
            ),
            RiskCategory(
                name="concentration_risk",
                display_name="Concentration Risk",
                description="Risks from over-concentration",
                indicators=["customer concentration", "supplier concentration", "geographic concentration"],
                required_level=4,
            ),
        ]
        return [r for r in all_risks if r.required_level <= level]
