import { useState } from 'react';
import { ChevronDown, ChevronRight, BookOpen, Target, AlertTriangle } from 'lucide-react';

type ProfileCode = 'vc' | 'pharma' | 'insurance' | 'general';
type ExtractionLevel = 1 | 2 | 3 | 4;

interface MetricDefinition {
  name: string;
  displayName: string;
  description: string;
  unitType: string;
  requiredLevel: ExtractionLevel;
  calculationNotes?: string;
}

interface ClaimPredicate {
  name: string;
  displayName: string;
  description: string;
  subjectTypes: string[];
  objectTypes: string[];
  requiredLevel: ExtractionLevel;
}

interface RiskCategory {
  name: string;
  displayName: string;
  description: string;
  indicators: string[];
  requiredLevel: ExtractionLevel;
}

interface ProfileVocabulary {
  code: ProfileCode;
  name: string;
  description: string;
  metrics: MetricDefinition[];
  claimPredicates: ClaimPredicate[];
  riskCategories: RiskCategory[];
}

// Vocabulary data extracted from backend
const vocabularies: ProfileVocabulary[] = [
  {
    code: 'vc',
    name: 'Venture Capital',
    description: 'Startup due diligence, funding metrics, compliance claims, and investment risks',
    metrics: [
      { name: 'arr', displayName: 'ARR', description: 'Annual Recurring Revenue', unitType: 'currency', requiredLevel: 1, calculationNotes: 'MRR × 12' },
      { name: 'mrr', displayName: 'MRR', description: 'Monthly Recurring Revenue', unitType: 'currency', requiredLevel: 1 },
      { name: 'revenue', displayName: 'Revenue', description: 'Total revenue (including non-recurring)', unitType: 'currency', requiredLevel: 1 },
      { name: 'burn', displayName: 'Burn Rate', description: 'Monthly cash burn rate', unitType: 'currency', requiredLevel: 1 },
      { name: 'runway', displayName: 'Runway', description: 'Months of runway remaining', unitType: 'duration', requiredLevel: 1, calculationNotes: 'Cash / Monthly Burn' },
      { name: 'cash', displayName: 'Cash', description: 'Cash and cash equivalents', unitType: 'currency', requiredLevel: 1 },
      { name: 'headcount', displayName: 'Headcount', description: 'Total employees', unitType: 'count', requiredLevel: 1 },
      { name: 'growth_rate', displayName: 'Growth Rate', description: 'Revenue/ARR growth rate', unitType: 'percentage', requiredLevel: 2 },
      { name: 'nrr', displayName: 'NRR', description: 'Net Revenue Retention', unitType: 'percentage', requiredLevel: 2, calculationNotes: '(Starting MRR + Expansion - Contraction - Churn) / Starting MRR' },
      { name: 'grr', displayName: 'GRR', description: 'Gross Revenue Retention', unitType: 'percentage', requiredLevel: 2 },
      { name: 'churn', displayName: 'Churn Rate', description: 'Customer or revenue churn rate', unitType: 'percentage', requiredLevel: 2 },
      { name: 'gross_margin', displayName: 'Gross Margin', description: 'Gross profit margin', unitType: 'percentage', requiredLevel: 2 },
      { name: 'cac', displayName: 'CAC', description: 'Customer Acquisition Cost', unitType: 'currency', requiredLevel: 3 },
      { name: 'ltv', displayName: 'LTV', description: 'Customer Lifetime Value', unitType: 'currency', requiredLevel: 3 },
      { name: 'ltv_cac_ratio', displayName: 'LTV/CAC Ratio', description: 'LTV to CAC ratio', unitType: 'ratio', requiredLevel: 3, calculationNotes: 'Target: >3x' },
      { name: 'cac_payback', displayName: 'CAC Payback', description: 'Months to recover CAC', unitType: 'duration', requiredLevel: 3 },
      { name: 'magic_number', displayName: 'Magic Number', description: 'Sales efficiency metric', unitType: 'ratio', requiredLevel: 3, calculationNotes: 'Net New ARR / S&M Spend (previous quarter)' },
      { name: 'arpu', displayName: 'ARPU', description: 'Average Revenue Per User', unitType: 'currency', requiredLevel: 3 },
      { name: 'dau', displayName: 'DAU', description: 'Daily Active Users', unitType: 'count', requiredLevel: 3 },
      { name: 'mau', displayName: 'MAU', description: 'Monthly Active Users', unitType: 'count', requiredLevel: 3 },
      { name: 'burn_multiple', displayName: 'Burn Multiple', description: 'Net burn divided by net new ARR', unitType: 'ratio', requiredLevel: 4, calculationNotes: 'Net Burn / Net New ARR (lower is better)' },
      { name: 'rule_of_40', displayName: 'Rule of 40', description: 'Growth rate + profit margin', unitType: 'percentage', requiredLevel: 4, calculationNotes: 'Revenue Growth % + EBITDA Margin %' },
      { name: 'quick_ratio', displayName: 'Quick Ratio (SaaS)', description: 'SaaS Quick Ratio', unitType: 'ratio', requiredLevel: 4, calculationNotes: '(New MRR + Expansion MRR) / (Contraction MRR + Churn MRR)' },
    ],
    claimPredicates: [
      { name: 'has_soc2', displayName: 'Has SOC2', description: 'Company has SOC2 certification', subjectTypes: ['company'], objectTypes: ['certification'], requiredLevel: 1 },
      { name: 'is_iso27001', displayName: 'ISO 27001 Certified', description: 'Company has ISO 27001 certification', subjectTypes: ['company'], objectTypes: ['certification'], requiredLevel: 1 },
      { name: 'is_gdpr_compliant', displayName: 'GDPR Compliant', description: 'Company claims GDPR compliance', subjectTypes: ['company', 'product'], objectTypes: ['regulation'], requiredLevel: 1 },
      { name: 'is_hipaa_compliant', displayName: 'HIPAA Compliant', description: 'Company claims HIPAA compliance', subjectTypes: ['company', 'product'], objectTypes: ['regulation'], requiredLevel: 1 },
      { name: 'owns_ip', displayName: 'Owns IP', description: 'Company owns intellectual property', subjectTypes: ['company', 'founder'], objectTypes: ['patent', 'trademark', 'copyright', 'trade_secret'], requiredLevel: 2 },
      { name: 'has_customer', displayName: 'Has Customer', description: 'Company has specific customer', subjectTypes: ['company'], objectTypes: ['company', 'organization'], requiredLevel: 2 },
      { name: 'has_partnership', displayName: 'Has Partnership', description: 'Company has partnership agreement', subjectTypes: ['company'], objectTypes: ['company', 'organization'], requiredLevel: 2 },
      { name: 'raised_funding', displayName: 'Raised Funding', description: 'Company raised funding round', subjectTypes: ['company'], objectTypes: ['funding_round'], requiredLevel: 2 },
      { name: 'has_security_incident', displayName: 'Security Incident', description: 'Company experienced security incident', subjectTypes: ['company'], objectTypes: ['incident'], requiredLevel: 3 },
      { name: 'has_pending_litigation', displayName: 'Pending Litigation', description: 'Company has pending litigation', subjectTypes: ['company', 'founder'], objectTypes: ['litigation'], requiredLevel: 3 },
      { name: 'founder_prior_exit', displayName: 'Founder Prior Exit', description: 'Founder has prior successful exit', subjectTypes: ['founder'], objectTypes: ['company', 'exit_event'], requiredLevel: 3 },
      { name: 'related_party_transaction', displayName: 'Related Party Transaction', description: 'Related party transaction exists', subjectTypes: ['company', 'founder', 'investor'], objectTypes: ['transaction'], requiredLevel: 4 },
      { name: 'cap_table_issue', displayName: 'Cap Table Issue', description: 'Cap table has issues', subjectTypes: ['company'], objectTypes: ['issue'], requiredLevel: 4 },
    ],
    riskCategories: [
      { name: 'runway_risk', displayName: 'Runway Risk', description: 'Risk of running out of cash', indicators: ['runway < 12 months', 'increasing burn rate', 'missed fundraising targets'], requiredLevel: 2 },
      { name: 'customer_concentration', displayName: 'Customer Concentration', description: 'Over-reliance on few customers', indicators: ['single customer > 20% revenue', 'top 3 customers > 50% revenue'], requiredLevel: 2 },
      { name: 'key_person_risk', displayName: 'Key Person Risk', description: 'Dependency on key individuals', indicators: ['single founder', 'no succession plan', 'critical knowledge in one person'], requiredLevel: 2 },
      { name: 'compliance_gap', displayName: 'Compliance Gap', description: 'Missing required certifications', indicators: ['enterprise sales without SOC2', 'healthcare vertical without HIPAA', 'EU customers without GDPR compliance'], requiredLevel: 2 },
      { name: 'ip_risk', displayName: 'IP Risk', description: 'Intellectual property risks', indicators: ['IP not assigned to company', 'founder IP from prior employer', 'open source license conflicts'], requiredLevel: 3 },
      { name: 'market_risk', displayName: 'Market Risk', description: 'Market/competitive risks', indicators: ['declining TAM', 'well-funded competitors', 'regulatory headwinds'], requiredLevel: 3 },
      { name: 'technical_debt', displayName: 'Technical Debt', description: 'Technical/product risks', indicators: ['legacy architecture', 'security vulnerabilities', 'scalability concerns'], requiredLevel: 3 },
      { name: 'churn_risk', displayName: 'Churn Risk', description: 'Customer retention risks', indicators: ['NRR < 100%', 'increasing churn trend', 'low customer satisfaction'], requiredLevel: 3 },
      { name: 'governance_risk', displayName: 'Governance Risk', description: 'Corporate governance concerns', indicators: ['related party transactions', 'board composition issues', 'missing controls'], requiredLevel: 4 },
      { name: 'financial_irregularity', displayName: 'Financial Irregularity', description: 'Accounting/financial concerns', indicators: ['revenue recognition issues', 'expense timing manipulation', 'inconsistent metrics'], requiredLevel: 4 },
      { name: 'cap_table_risk', displayName: 'Cap Table Risk', description: 'Capitalization issues', indicators: ['option pool too small', 'liquidation preference stacking', 'founder dilution'], requiredLevel: 4 },
    ],
  },
  {
    code: 'pharma',
    name: 'Pharmaceutical / Life Sciences',
    description: 'Drug development, clinical trials, regulatory compliance, and biotech investments',
    metrics: [
      { name: 'revenue', displayName: 'Revenue', description: 'Total revenue', unitType: 'currency', requiredLevel: 1 },
      { name: 'rd_spend', displayName: 'R&D Spend', description: 'Research and development expenditure', unitType: 'currency', requiredLevel: 1 },
      { name: 'pipeline_count', displayName: 'Pipeline Count', description: 'Number of drugs in development pipeline', unitType: 'count', requiredLevel: 1 },
      { name: 'cash', displayName: 'Cash Position', description: 'Cash and cash equivalents', unitType: 'currency', requiredLevel: 1 },
      { name: 'burn', displayName: 'Cash Burn', description: 'Monthly/quarterly cash burn rate', unitType: 'currency', requiredLevel: 1 },
      { name: 'clinical_trial_count', displayName: 'Clinical Trials', description: 'Number of active clinical trials', unitType: 'count', requiredLevel: 2 },
      { name: 'phase1_count', displayName: 'Phase 1 Candidates', description: 'Drugs in Phase 1 trials', unitType: 'count', requiredLevel: 2 },
      { name: 'phase2_count', displayName: 'Phase 2 Candidates', description: 'Drugs in Phase 2 trials', unitType: 'count', requiredLevel: 2 },
      { name: 'phase3_count', displayName: 'Phase 3 Candidates', description: 'Drugs in Phase 3 trials', unitType: 'count', requiredLevel: 2 },
      { name: 'approved_drugs', displayName: 'Approved Drugs', description: 'Number of FDA/EMA approved drugs', unitType: 'count', requiredLevel: 2 },
      { name: 'patent_count', displayName: 'Patent Count', description: 'Number of active patents', unitType: 'count', requiredLevel: 2 },
      { name: 'patient_enrollment', displayName: 'Patient Enrollment', description: 'Total patients enrolled in trials', unitType: 'count', requiredLevel: 3 },
      { name: 'efficacy_rate', displayName: 'Efficacy Rate', description: 'Primary endpoint success rate', unitType: 'percentage', requiredLevel: 3 },
      { name: 'safety_events', displayName: 'Safety Events', description: 'Serious adverse events count', unitType: 'count', requiredLevel: 3 },
      { name: 'manufacturing_capacity', displayName: 'Manufacturing Capacity', description: 'Production capacity', unitType: 'count', requiredLevel: 3 },
      { name: 'tam', displayName: 'Total Addressable Market', description: 'Market size for target indications', unitType: 'currency', requiredLevel: 3 },
      { name: 'cost_per_patient', displayName: 'Cost Per Patient', description: 'Trial cost per enrolled patient', unitType: 'currency', requiredLevel: 4 },
      { name: 'time_to_market', displayName: 'Time to Market', description: 'Estimated months to FDA approval', unitType: 'duration', requiredLevel: 4 },
      { name: 'peak_sales', displayName: 'Peak Sales Estimate', description: 'Projected peak annual sales', unitType: 'currency', requiredLevel: 4 },
    ],
    claimPredicates: [
      { name: 'has_fda_approval', displayName: 'FDA Approved', description: 'Drug has FDA approval', subjectTypes: ['drug', 'product'], objectTypes: ['approval'], requiredLevel: 1 },
      { name: 'has_ema_approval', displayName: 'EMA Approved', description: 'Drug has EMA approval', subjectTypes: ['drug', 'product'], objectTypes: ['approval'], requiredLevel: 1 },
      { name: 'gmp_compliant', displayName: 'GMP Compliant', description: 'Manufacturing is GMP compliant', subjectTypes: ['company', 'facility'], objectTypes: ['certification'], requiredLevel: 1 },
      { name: 'has_ind', displayName: 'Has IND', description: 'Drug has Investigational New Drug application', subjectTypes: ['drug', 'product'], objectTypes: ['regulatory_filing'], requiredLevel: 1 },
      { name: 'in_clinical_trial', displayName: 'In Clinical Trial', description: 'Drug is in clinical trial phase', subjectTypes: ['drug', 'product'], objectTypes: ['trial_phase'], requiredLevel: 2 },
      { name: 'has_patent', displayName: 'Has Patent', description: 'Company/drug has patent protection', subjectTypes: ['company', 'drug', 'product'], objectTypes: ['patent'], requiredLevel: 2 },
      { name: 'orphan_designation', displayName: 'Orphan Designation', description: 'Drug has orphan drug designation', subjectTypes: ['drug', 'product'], objectTypes: ['designation'], requiredLevel: 2 },
      { name: 'breakthrough_designation', displayName: 'Breakthrough Designation', description: 'Drug has breakthrough therapy designation', subjectTypes: ['drug', 'product'], objectTypes: ['designation'], requiredLevel: 2 },
      { name: 'fast_track_designation', displayName: 'Fast Track', description: 'Drug has fast track designation', subjectTypes: ['drug', 'product'], objectTypes: ['designation'], requiredLevel: 2 },
      { name: 'received_crl', displayName: 'Received CRL', description: 'Drug received Complete Response Letter', subjectTypes: ['drug', 'product'], objectTypes: ['regulatory_action'], requiredLevel: 3 },
      { name: 'fda_warning_letter', displayName: 'FDA Warning Letter', description: 'Facility received FDA warning letter', subjectTypes: ['company', 'facility'], objectTypes: ['regulatory_action'], requiredLevel: 3 },
      { name: 'clinical_hold', displayName: 'Clinical Hold', description: 'Trial placed on clinical hold', subjectTypes: ['drug', 'trial'], objectTypes: ['regulatory_action'], requiredLevel: 3 },
      { name: 'has_licensing_agreement', displayName: 'Licensing Agreement', description: 'Has drug licensing agreement', subjectTypes: ['company'], objectTypes: ['company', 'agreement'], requiredLevel: 3 },
      { name: 'data_integrity_issue', displayName: 'Data Integrity Issue', description: 'Clinical data integrity concerns', subjectTypes: ['trial', 'company'], objectTypes: ['issue'], requiredLevel: 4 },
      { name: 'manufacturing_deviation', displayName: 'Manufacturing Deviation', description: 'Manufacturing process deviation', subjectTypes: ['facility', 'product'], objectTypes: ['deviation'], requiredLevel: 4 },
    ],
    riskCategories: [
      { name: 'clinical_risk', displayName: 'Clinical Risk', description: 'Risk of clinical trial failure', indicators: ['failed primary endpoint', 'safety signals', 'enrollment challenges', 'protocol amendments'], requiredLevel: 2 },
      { name: 'regulatory_risk', displayName: 'Regulatory Risk', description: 'Risk of regulatory setback', indicators: ['complete response letter', 'REMS requirements', 'post-market requirements'], requiredLevel: 2 },
      { name: 'ip_risk', displayName: 'IP/Patent Risk', description: 'Intellectual property risks', indicators: ['patent expiration', 'patent litigation', 'freedom to operate issues'], requiredLevel: 2 },
      { name: 'competition_risk', displayName: 'Competition Risk', description: 'Competitive landscape risks', indicators: ['multiple competitors in same indication', 'biosimilar threat', 'generic entry'], requiredLevel: 2 },
      { name: 'manufacturing_risk', displayName: 'Manufacturing Risk', description: 'Drug manufacturing risks', indicators: ['single CMO dependency', 'supply chain issues', 'scale-up challenges', 'FDA warning letters'], requiredLevel: 3 },
      { name: 'reimbursement_risk', displayName: 'Reimbursement Risk', description: 'Payer coverage/pricing risks', indicators: ['ICER unfavorable review', 'formulary exclusions', 'price negotiations'], requiredLevel: 3 },
      { name: 'safety_risk', displayName: 'Safety Risk', description: 'Drug safety concerns', indicators: ['black box warning', 'serious adverse events', 'post-market safety signals'], requiredLevel: 3 },
      { name: 'key_opinion_leader_risk', displayName: 'KOL Risk', description: 'Key opinion leader concerns', indicators: ['negative KOL sentiment', 'competing therapy preference'], requiredLevel: 3 },
      { name: 'data_integrity_risk', displayName: 'Data Integrity Risk', description: 'Clinical data integrity concerns', indicators: ['site inspection findings', 'data manipulation suspicions', 'GCP violations'], requiredLevel: 4 },
      { name: 'compliance_risk', displayName: 'Compliance Risk', description: 'Regulatory compliance concerns', indicators: ['consent decree', 'corporate integrity agreement', 'DOJ investigation'], requiredLevel: 4 },
      { name: 'commercial_viability_risk', displayName: 'Commercial Viability Risk', description: 'Market/commercial risks', indicators: ['market size overestimation', 'pricing pressure', 'patient access barriers'], requiredLevel: 4 },
    ],
  },
  {
    code: 'insurance',
    name: 'Insurance',
    description: 'Underwriting, claims analysis, risk assessment, and regulatory compliance',
    metrics: [
      { name: 'revenue', displayName: 'Revenue', description: 'Total revenue / gross written premium', unitType: 'currency', requiredLevel: 1 },
      { name: 'net_income', displayName: 'Net Income', description: 'Net income / profit', unitType: 'currency', requiredLevel: 1 },
      { name: 'assets', displayName: 'Total Assets', description: 'Total assets under management', unitType: 'currency', requiredLevel: 1 },
      { name: 'policyholder_surplus', displayName: 'Policyholder Surplus', description: 'Policyholder surplus / capital', unitType: 'currency', requiredLevel: 1 },
      { name: 'policy_count', displayName: 'Policy Count', description: 'Number of active policies', unitType: 'count', requiredLevel: 1 },
      { name: 'combined_ratio', displayName: 'Combined Ratio', description: 'Loss ratio + expense ratio', unitType: 'percentage', requiredLevel: 2, calculationNotes: '< 100% indicates underwriting profit' },
      { name: 'loss_ratio', displayName: 'Loss Ratio', description: 'Incurred losses / earned premium', unitType: 'percentage', requiredLevel: 2 },
      { name: 'expense_ratio', displayName: 'Expense Ratio', description: 'Underwriting expenses / written premium', unitType: 'percentage', requiredLevel: 2 },
      { name: 'rbc_ratio', displayName: 'RBC Ratio', description: 'Risk-Based Capital ratio', unitType: 'percentage', requiredLevel: 2, calculationNotes: 'Regulatory minimum is 200%' },
      { name: 'investment_yield', displayName: 'Investment Yield', description: 'Return on invested assets', unitType: 'percentage', requiredLevel: 2 },
      { name: 'roe', displayName: 'Return on Equity', description: 'Return on shareholders\' equity', unitType: 'percentage', requiredLevel: 3 },
      { name: 'retention_ratio', displayName: 'Retention Ratio', description: 'Policy retention/renewal rate', unitType: 'percentage', requiredLevel: 3 },
      { name: 'claims_frequency', displayName: 'Claims Frequency', description: 'Claims per policy period', unitType: 'ratio', requiredLevel: 3 },
      { name: 'claims_severity', displayName: 'Claims Severity', description: 'Average claim amount', unitType: 'currency', requiredLevel: 3 },
      { name: 'reserves', displayName: 'Loss Reserves', description: 'Total loss reserves', unitType: 'currency', requiredLevel: 3 },
      { name: 'reserve_development', displayName: 'Reserve Development', description: 'Prior year reserve development', unitType: 'currency', requiredLevel: 3 },
      { name: 'ibnr', displayName: 'IBNR', description: 'Incurred But Not Reported reserves', unitType: 'currency', requiredLevel: 4 },
      { name: 'pml', displayName: 'Probable Maximum Loss', description: 'Probable Maximum Loss estimate', unitType: 'currency', requiredLevel: 4 },
      { name: 'var', displayName: 'Value at Risk', description: 'Value at Risk for portfolio', unitType: 'currency', requiredLevel: 4 },
      { name: 'cat_exposure', displayName: 'Catastrophe Exposure', description: 'Total catastrophe exposure', unitType: 'currency', requiredLevel: 4 },
    ],
    claimPredicates: [
      { name: 'licensed_in', displayName: 'Licensed In', description: 'Company licensed to operate in jurisdiction', subjectTypes: ['company'], objectTypes: ['jurisdiction', 'state'], requiredLevel: 1 },
      { name: 'am_best_rating', displayName: 'AM Best Rating', description: 'Company has AM Best rating', subjectTypes: ['company'], objectTypes: ['rating'], requiredLevel: 1 },
      { name: 'sp_rating', displayName: 'S&P Rating', description: 'Company has S&P rating', subjectTypes: ['company'], objectTypes: ['rating'], requiredLevel: 1 },
      { name: 'offers_line', displayName: 'Offers Line of Business', description: 'Company writes specific line of insurance', subjectTypes: ['company'], objectTypes: ['line_of_business'], requiredLevel: 1 },
      { name: 'has_reinsurance', displayName: 'Has Reinsurance', description: 'Company has reinsurance arrangement', subjectTypes: ['company'], objectTypes: ['reinsurer', 'treaty'], requiredLevel: 2 },
      { name: 'regulatory_action', displayName: 'Regulatory Action', description: 'Company subject to regulatory action', subjectTypes: ['company'], objectTypes: ['action', 'order'], requiredLevel: 2 },
      { name: 'market_conduct_exam', displayName: 'Market Conduct Exam', description: 'Company underwent market conduct exam', subjectTypes: ['company'], objectTypes: ['exam', 'finding'], requiredLevel: 2 },
      { name: 'affiliated_with', displayName: 'Affiliated With', description: 'Company part of insurance group', subjectTypes: ['company'], objectTypes: ['company', 'group'], requiredLevel: 2 },
      { name: 'rate_filing_approved', displayName: 'Rate Filing Approved', description: 'Rate filing approved by regulator', subjectTypes: ['company', 'product'], objectTypes: ['filing', 'rate'], requiredLevel: 3 },
      { name: 'form_filing_approved', displayName: 'Form Filing Approved', description: 'Policy form approved by regulator', subjectTypes: ['company', 'product'], objectTypes: ['form'], requiredLevel: 3 },
      { name: 'complaint_ratio', displayName: 'Complaint Ratio', description: 'Company complaint ratio vs industry', subjectTypes: ['company'], objectTypes: ['ratio', 'ranking'], requiredLevel: 3 },
      { name: 'consent_order', displayName: 'Consent Order', description: 'Company under consent order', subjectTypes: ['company'], objectTypes: ['order'], requiredLevel: 3 },
      { name: 'reserve_deficiency', displayName: 'Reserve Deficiency', description: 'Actuarial reserve deficiency identified', subjectTypes: ['company'], objectTypes: ['deficiency'], requiredLevel: 4 },
      { name: 'related_party_transaction', displayName: 'Related Party Transaction', description: 'Related party transaction exists', subjectTypes: ['company'], objectTypes: ['transaction'], requiredLevel: 4 },
      { name: 'restatement', displayName: 'Financial Restatement', description: 'Financial statements restated', subjectTypes: ['company'], objectTypes: ['restatement'], requiredLevel: 4 },
    ],
    riskCategories: [
      { name: 'underwriting_risk', displayName: 'Underwriting Risk', description: 'Risk from underwriting performance', indicators: ['combined ratio > 100%', 'deteriorating loss ratio', 'inadequate pricing'], requiredLevel: 2 },
      { name: 'reserve_risk', displayName: 'Reserve Risk', description: 'Risk of inadequate reserves', indicators: ['adverse reserve development', 'IBNR uncertainty', 'long-tail exposure'], requiredLevel: 2 },
      { name: 'capital_adequacy_risk', displayName: 'Capital Adequacy Risk', description: 'Risk of insufficient capital', indicators: ['RBC ratio declining', 'surplus strain', 'high leverage'], requiredLevel: 2 },
      { name: 'concentration_risk', displayName: 'Concentration Risk', description: 'Geographic or line of business concentration', indicators: ['single state > 50% premium', 'single line dominance', 'large account dependency'], requiredLevel: 2 },
      { name: 'catastrophe_risk', displayName: 'Catastrophe Risk', description: 'Exposure to catastrophic events', indicators: ['hurricane exposure', 'earthquake exposure', 'cyber aggregation', 'inadequate reinsurance'], requiredLevel: 3 },
      { name: 'investment_risk', displayName: 'Investment Risk', description: 'Risk from investment portfolio', indicators: ['credit downgrades', 'illiquid investments', 'duration mismatch'], requiredLevel: 3 },
      { name: 'reinsurance_risk', displayName: 'Reinsurance Risk', description: 'Reinsurance counterparty/coverage risk', indicators: ['reinsurer credit risk', 'coverage gaps', 'treaty exhaustion'], requiredLevel: 3 },
      { name: 'regulatory_risk', displayName: 'Regulatory Risk', description: 'Risk from regulatory actions', indicators: ['market conduct findings', 'rate disapprovals', 'consent orders'], requiredLevel: 3 },
      { name: 'operational_risk', displayName: 'Operational Risk', description: 'Operational and systems risks', indicators: ['system failures', 'vendor dependency', 'claims handling issues'], requiredLevel: 3 },
      { name: 'fraud_risk', displayName: 'Fraud Risk', description: 'Risk of fraudulent activity', indicators: ['claims fraud patterns', 'agent misconduct', 'financial irregularities'], requiredLevel: 4 },
      { name: 'actuarial_risk', displayName: 'Actuarial Risk', description: 'Actuarial methodology concerns', indicators: ['reserve methodology changes', 'assumption changes', 'actuarial opinion qualifications'], requiredLevel: 4 },
      { name: 'governance_risk', displayName: 'Governance Risk', description: 'Corporate governance concerns', indicators: ['board composition', 'related party transactions', 'holding company issues'], requiredLevel: 4 },
      { name: 'run_off_risk', displayName: 'Run-off Risk', description: 'Risk from discontinued operations', indicators: ['asbestos exposure', 'environmental claims', 'long-tail reserves'], requiredLevel: 4 },
    ],
  },
  {
    code: 'general',
    name: 'General',
    description: 'Generic document analysis for cross-domain extraction',
    metrics: [
      { name: 'revenue', displayName: 'Revenue', description: 'Total revenue or sales', unitType: 'currency', requiredLevel: 1 },
      { name: 'profit', displayName: 'Profit', description: 'Net profit or net income', unitType: 'currency', requiredLevel: 1 },
      { name: 'headcount', displayName: 'Headcount', description: 'Total number of employees', unitType: 'count', requiredLevel: 1 },
      { name: 'gross_margin', displayName: 'Gross Margin', description: 'Gross profit as percentage of revenue', unitType: 'percentage', requiredLevel: 2 },
      { name: 'operating_margin', displayName: 'Operating Margin', description: 'Operating income as percentage of revenue', unitType: 'percentage', requiredLevel: 2 },
      { name: 'ebitda', displayName: 'EBITDA', description: 'Earnings before interest, taxes, depreciation, and amortization', unitType: 'currency', requiredLevel: 2 },
      { name: 'cash', displayName: 'Cash', description: 'Cash and cash equivalents', unitType: 'currency', requiredLevel: 2 },
      { name: 'debt', displayName: 'Total Debt', description: 'Total debt obligations', unitType: 'currency', requiredLevel: 3 },
      { name: 'assets', displayName: 'Total Assets', description: 'Total assets on balance sheet', unitType: 'currency', requiredLevel: 3 },
      { name: 'liabilities', displayName: 'Total Liabilities', description: 'Total liabilities on balance sheet', unitType: 'currency', requiredLevel: 3 },
      { name: 'equity', displayName: 'Shareholders\' Equity', description: 'Total shareholders\' equity', unitType: 'currency', requiredLevel: 3 },
      { name: 'working_capital', displayName: 'Working Capital', description: 'Current assets minus current liabilities', unitType: 'currency', requiredLevel: 4 },
      { name: 'capex', displayName: 'Capital Expenditure', description: 'Capital expenditure', unitType: 'currency', requiredLevel: 4 },
    ],
    claimPredicates: [
      { name: 'has_certification', displayName: 'Has Certification', description: 'Entity holds a certification', subjectTypes: ['company', 'organization', 'product'], objectTypes: ['certification'], requiredLevel: 1 },
      { name: 'is_compliant_with', displayName: 'Is Compliant With', description: 'Entity is compliant with regulation/standard', subjectTypes: ['company', 'organization', 'product', 'process'], objectTypes: ['regulation', 'standard', 'framework'], requiredLevel: 1 },
      { name: 'operates_in', displayName: 'Operates In', description: 'Entity operates in region/market', subjectTypes: ['company', 'organization'], objectTypes: ['region', 'market', 'jurisdiction'], requiredLevel: 1 },
      { name: 'has_policy', displayName: 'Has Policy', description: 'Entity has a specific policy in place', subjectTypes: ['company', 'organization'], objectTypes: ['policy'], requiredLevel: 2 },
      { name: 'underwent_audit', displayName: 'Underwent Audit', description: 'Entity underwent audit', subjectTypes: ['company', 'organization', 'process'], objectTypes: ['audit_type'], requiredLevel: 2 },
      { name: 'has_contract_with', displayName: 'Has Contract With', description: 'Entity has contractual relationship', subjectTypes: ['company', 'organization'], objectTypes: ['company', 'organization'], requiredLevel: 2 },
      { name: 'owns_ip', displayName: 'Owns IP', description: 'Entity owns intellectual property', subjectTypes: ['company', 'organization', 'person'], objectTypes: ['patent', 'trademark', 'copyright', 'trade_secret'], requiredLevel: 3 },
      { name: 'has_liability', displayName: 'Has Liability', description: 'Entity has legal/financial liability', subjectTypes: ['company', 'organization'], objectTypes: ['liability_type'], requiredLevel: 3 },
      { name: 'experienced_incident', displayName: 'Experienced Incident', description: 'Entity experienced security/operational incident', subjectTypes: ['company', 'organization'], objectTypes: ['incident_type'], requiredLevel: 3 },
      { name: 'related_party_transaction', displayName: 'Related Party Transaction', description: 'Entity engaged in related party transaction', subjectTypes: ['company', 'organization', 'person'], objectTypes: ['transaction'], requiredLevel: 4 },
      { name: 'has_contingency', displayName: 'Has Contingency', description: 'Entity has contingent liability/asset', subjectTypes: ['company', 'organization'], objectTypes: ['contingency'], requiredLevel: 4 },
    ],
    riskCategories: [
      { name: 'financial_risk', displayName: 'Financial Risk', description: 'Risks related to financial position or performance', indicators: ['declining revenue', 'cash burn', 'debt covenants', 'liquidity concerns'], requiredLevel: 2 },
      { name: 'compliance_risk', displayName: 'Compliance Risk', description: 'Risks related to regulatory compliance', indicators: ['regulatory violations', 'audit findings', 'pending investigations'], requiredLevel: 2 },
      { name: 'operational_risk', displayName: 'Operational Risk', description: 'Risks related to business operations', indicators: ['supply chain issues', 'key person dependency', 'system failures'], requiredLevel: 2 },
      { name: 'legal_risk', displayName: 'Legal Risk', description: 'Risks from litigation or legal issues', indicators: ['pending lawsuits', 'regulatory actions', 'contract disputes'], requiredLevel: 3 },
      { name: 'reputational_risk', displayName: 'Reputational Risk', description: 'Risks to reputation or brand', indicators: ['negative press', 'customer complaints', 'executive misconduct'], requiredLevel: 3 },
      { name: 'cyber_risk', displayName: 'Cyber Risk', description: 'Risks from cybersecurity threats', indicators: ['data breaches', 'ransomware', 'system vulnerabilities'], requiredLevel: 3 },
      { name: 'fraud_risk', displayName: 'Fraud Risk', description: 'Risks from fraudulent activity', indicators: ['accounting irregularities', 'unusual transactions', 'whistleblower reports'], requiredLevel: 4 },
      { name: 'concentration_risk', displayName: 'Concentration Risk', description: 'Risks from over-concentration', indicators: ['customer concentration', 'supplier concentration', 'geographic concentration'], requiredLevel: 4 },
    ],
  },
];

const levelDescriptions: Record<ExtractionLevel, { name: string; description: string }> = {
  1: { name: 'Basic', description: 'Essential metrics and compliance claims only' },
  2: { name: 'Standard', description: 'Comprehensive metrics with time scope, all compliance claims' },
  3: { name: 'Deep', description: 'All metrics, entity resolution, time-series data, risk identification' },
  4: { name: 'Forensic', description: 'Maximum extraction depth, all inconsistencies flagged' },
};

const levelColors: Record<ExtractionLevel, string> = {
  1: 'bg-green-100 text-green-800',
  2: 'bg-blue-100 text-blue-800',
  3: 'bg-purple-100 text-purple-800',
  4: 'bg-red-100 text-red-800',
};

function LevelBadge({ level }: { level: ExtractionLevel }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${levelColors[level]}`}>
      L{level}
    </span>
  );
}

function CollapsibleSection({
  title,
  icon: Icon,
  children,
  defaultOpen = false,
  count,
}: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
  defaultOpen?: boolean;
  count?: number;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Icon className="h-5 w-5 text-gray-500" />
          <span className="font-medium text-gray-900">{title}</span>
          {count !== undefined && (
            <span className="text-sm text-gray-500">({count})</span>
          )}
        </div>
        {isOpen ? (
          <ChevronDown className="h-5 w-5 text-gray-400" />
        ) : (
          <ChevronRight className="h-5 w-5 text-gray-400" />
        )}
      </button>
      {isOpen && <div className="p-4">{children}</div>}
    </div>
  );
}

function MetricsTable({ metrics }: { metrics: MetricDefinition[] }) {
  const groupedByLevel = metrics.reduce(
    (acc, metric) => {
      if (!acc[metric.requiredLevel]) {
        acc[metric.requiredLevel] = [];
      }
      acc[metric.requiredLevel].push(metric);
      return acc;
    },
    {} as Record<ExtractionLevel, MetricDefinition[]>
  );

  return (
    <div className="space-y-4">
      {([1, 2, 3, 4] as ExtractionLevel[]).map((level) => {
        const levelMetrics = groupedByLevel[level];
        if (!levelMetrics?.length) return null;

        return (
          <div key={level}>
            <div className="flex items-center gap-2 mb-2">
              <LevelBadge level={level} />
              <span className="text-sm text-gray-600">
                {levelDescriptions[level].name} - {levelDescriptions[level].description}
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Unit</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Notes</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {levelMetrics.map((metric) => (
                    <tr key={metric.name} className="hover:bg-gray-50">
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className="font-mono text-sm text-gray-900">{metric.displayName}</span>
                      </td>
                      <td className="px-3 py-2 text-sm text-gray-600">{metric.description}</td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className="text-xs bg-gray-100 px-2 py-1 rounded">{metric.unitType}</span>
                      </td>
                      <td className="px-3 py-2 text-sm text-gray-500">{metric.calculationNotes || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ClaimsTable({ claims }: { claims: ClaimPredicate[] }) {
  const groupedByLevel = claims.reduce(
    (acc, claim) => {
      if (!acc[claim.requiredLevel]) {
        acc[claim.requiredLevel] = [];
      }
      acc[claim.requiredLevel].push(claim);
      return acc;
    },
    {} as Record<ExtractionLevel, ClaimPredicate[]>
  );

  return (
    <div className="space-y-4">
      {([1, 2, 3, 4] as ExtractionLevel[]).map((level) => {
        const levelClaims = groupedByLevel[level];
        if (!levelClaims?.length) return null;

        return (
          <div key={level}>
            <div className="flex items-center gap-2 mb-2">
              <LevelBadge level={level} />
              <span className="text-sm text-gray-600">{levelDescriptions[level].name}</span>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Predicate</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Subject Types</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Object Types</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {levelClaims.map((claim) => (
                    <tr key={claim.name} className="hover:bg-gray-50">
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className="font-mono text-sm text-gray-900">{claim.name}</span>
                      </td>
                      <td className="px-3 py-2 text-sm text-gray-600">{claim.description}</td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-1">
                          {claim.subjectTypes.map((t) => (
                            <span key={t} className="text-xs bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded">
                              {t}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap gap-1">
                          {claim.objectTypes.map((t) => (
                            <span key={t} className="text-xs bg-green-50 text-green-700 px-1.5 py-0.5 rounded">
                              {t}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RisksTable({ risks }: { risks: RiskCategory[] }) {
  const groupedByLevel = risks.reduce(
    (acc, risk) => {
      if (!acc[risk.requiredLevel]) {
        acc[risk.requiredLevel] = [];
      }
      acc[risk.requiredLevel].push(risk);
      return acc;
    },
    {} as Record<ExtractionLevel, RiskCategory[]>
  );

  return (
    <div className="space-y-4">
      {([2, 3, 4] as ExtractionLevel[]).map((level) => {
        const levelRisks = groupedByLevel[level];
        if (!levelRisks?.length) return null;

        return (
          <div key={level}>
            <div className="flex items-center gap-2 mb-2">
              <LevelBadge level={level} />
              <span className="text-sm text-gray-600">{levelDescriptions[level].name}</span>
            </div>
            <div className="grid gap-3">
              {levelRisks.map((risk) => (
                <div key={risk.name} className="border border-gray-200 rounded-lg p-3 hover:bg-gray-50">
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="font-medium text-gray-900">{risk.displayName}</span>
                      <p className="text-sm text-gray-600 mt-0.5">{risk.description}</p>
                    </div>
                  </div>
                  <div className="mt-2">
                    <span className="text-xs text-gray-500 font-medium">Indicators:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {risk.indicators.map((indicator, i) => (
                        <span key={i} className="text-xs bg-amber-50 text-amber-700 px-2 py-0.5 rounded">
                          {indicator}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function Prompts() {
  const [selectedProfile, setSelectedProfile] = useState<ProfileCode>('vc');
  const profile = vocabularies.find((v) => v.code === selectedProfile)!;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Extraction Prompts</h1>
        <p className="mt-1 text-gray-600">
          View the extraction vocabulary used for claim extraction from documents, organized by industry profile.
        </p>
      </div>

      {/* Profile selector */}
      <div className="flex flex-wrap gap-2">
        {vocabularies.map((vocab) => (
          <button
            key={vocab.code}
            onClick={() => setSelectedProfile(vocab.code)}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              selectedProfile === vocab.code
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {vocab.name}
          </button>
        ))}
      </div>

      {/* Profile description */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h2 className="text-lg font-semibold text-gray-900">{profile.name}</h2>
        <p className="text-gray-600 mt-1">{profile.description}</p>
        <div className="flex gap-4 mt-3 text-sm text-gray-500">
          <span>{profile.metrics.length} metrics</span>
          <span>{profile.claimPredicates.length} claim predicates</span>
          <span>{profile.riskCategories.length} risk categories</span>
        </div>
      </div>

      {/* Extraction level legend */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-900 mb-3">Extraction Levels</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {([1, 2, 3, 4] as ExtractionLevel[]).map((level) => (
            <div key={level} className="flex items-start gap-2">
              <LevelBadge level={level} />
              <div>
                <span className="text-sm font-medium text-gray-900">{levelDescriptions[level].name}</span>
                <p className="text-xs text-gray-500">{levelDescriptions[level].description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Content sections */}
      <div className="space-y-4">
        <CollapsibleSection
          title="Metrics"
          icon={Target}
          defaultOpen={true}
          count={profile.metrics.length}
        >
          <MetricsTable metrics={profile.metrics} />
        </CollapsibleSection>

        <CollapsibleSection
          title="Claim Predicates"
          icon={BookOpen}
          count={profile.claimPredicates.length}
        >
          <ClaimsTable claims={profile.claimPredicates} />
        </CollapsibleSection>

        <CollapsibleSection
          title="Risk Categories"
          icon={AlertTriangle}
          count={profile.riskCategories.length}
        >
          <RisksTable risks={profile.riskCategories} />
        </CollapsibleSection>
      </div>
    </div>
  );
}
