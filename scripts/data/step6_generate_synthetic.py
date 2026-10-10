import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("GCI_DATA_DIR", REPO_ROOT / "data"))

def generate_synthetic_data(num_customers=5000, transactions_per_customer=30):
    np.random.seed(42)
    
    # ---------------------------------------------------------
    # 1. Customers, Hidden Traits & Exact Contract Vocabulary
    # ---------------------------------------------------------
    customer_ids = [f'C{str(i).zfill(5)}' for i in range(10000, 10000 + num_customers)]
    
    customers = pd.DataFrame({'customer_id': customer_ids})
    
    # Hidden traits
    customers['trait_eco'] = np.random.beta(2, 3, num_customers)
    customers['trait_digital'] = np.random.beta(2, 2, num_customers)
    customers['trait_car_dep'] = np.random.beta(3, 2, num_customers)
    customers['trait_home_own'] = np.random.rand(num_customers) > 0.35 

    # Exact contract.json vocabulary mapping
    customers['homeowner_status'] = np.where(customers['trait_home_own'], 'OWNER', 'TENANT')
    customers['has_vehicle'] = customers['trait_car_dep'] > 0.3
    customers['is_ev_owner'] = customers['has_vehicle'] & (customers['trait_eco'] > 0.8)
    customers['is_paperless'] = customers['trait_digital'] > 0.5
    customers['has_digital_banking'] = customers['trait_digital'] > 0.1
    customers['marketing_consent'] = np.random.rand(num_customers) > 0.15
    customers['credit_score'] = np.random.randint(500, 850, num_customers)
    customers['is_in_arrears'] = customers['credit_score'] < 550
    customers['delinquency_status'] = np.where(customers['is_in_arrears'], 'ARREARS', 'CURRENT')
    customers['age'] = np.random.randint(18, 85, num_customers)
    customers['uk_resident'] = True
    customers['compliance_status'] = 'CLEAR'
    
    # Baselines (6-month observation window basis)
    customers['baseline_electricity_kwh'] = (np.random.normal(2000, 400, num_customers) - (customers['trait_eco'] * 500)).clip(lower=500).round(1)
    customers['baseline_gas_kwh'] = np.where(
        customers['trait_eco'] > 0.8, 0,  
        (np.random.normal(6000, 1000, num_customers)).clip(min=0).round(1)
    )
    customers['annual_mileage'] = np.where(
        customers['has_vehicle'], 
        (np.random.normal(11000, 3000, num_customers)).clip(min=2000).round(0), 
        0
    )

    # ---------------------------------------------------------
    # 2. Multi-Product Take-up Labels (Realistic Intercepts)
    # ---------------------------------------------------------
    # Product numbering follows contract.json v2.1.0 / PS1 spec Section 2:
    #   GP01 = EV_FINANCE, GP02 = GREEN_HOME, GP03 = SOLAR_FINANCE, GP04 = PAPERLESS_BANKING
    # (An earlier version of this script used GP01 = Green Home, GP02 = Solar, GP03 = EV,
    #  which silently mislabelled every take_up_* column.)
    z_gp01 = -5.5 + (customers['trait_eco'] * 2.5) + (customers['annual_mileage'] / 5000)
    customers['prob_GP01'] = 1 / (1 + np.exp(-z_gp01))
    customers['take_up_GP01'] = (np.random.rand(num_customers) < customers['prob_GP01']) & customers['has_vehicle'] & ~customers['is_ev_owner']

    z_gp02 = -5.0 + (customers['trait_eco'] * 3.0) + (customers['baseline_gas_kwh'] / 5000)
    customers['prob_GP02'] = 1 / (1 + np.exp(-z_gp02))
    customers['take_up_GP02'] = (np.random.rand(num_customers) < customers['prob_GP02']) & (customers['homeowner_status'] == 'OWNER')

    z_gp03 = -5.5 + (customers['trait_eco'] * 3.5) + (customers['baseline_electricity_kwh'] / 2000)
    customers['prob_GP03'] = 1 / (1 + np.exp(-z_gp03))
    customers['take_up_GP03'] = (np.random.rand(num_customers) < customers['prob_GP03']) & (customers['homeowner_status'] == 'OWNER')

    z_gp04 = -3.0 + (customers['trait_eco'] * 1.5) + (customers['trait_digital'] * 2.0)
    customers['prob_GP04'] = 1 / (1 + np.exp(-z_gp04))
    customers['take_up_GP04'] = (np.random.rand(num_customers) < customers['prob_GP04']) & ~customers['is_paperless'] & customers['has_digital_banking']

    # ---------------------------------------------------------
    # 3. Time-Stamped Transactions (8 Categories & Leakage Prevention)
    # ---------------------------------------------------------
    cats = ['Fuel', 'Electricity', 'Gas', 'Public Transport', 'Home Improvement', 'Automotive', 'Utilities', 'Other']
    
    start_date = datetime(2026, 1, 1)
    end_date = datetime(2026, 6, 30)
    date_range = (end_date - start_date).days

    transactions = []
    tx_id_counter = 1000000

    for _, row in customers.iterrows():
        n_tx = np.random.randint(20, transactions_per_customer + 10)
        
        for _ in range(n_tx):
            if row['trait_eco'] > 0.7:
                probs = [0.05, 0.15, 0.05, 0.20, 0.10, 0.05, 0.10, 0.30] 
            elif row['trait_car_dep'] > 0.7:
                probs = [0.25, 0.10, 0.10, 0.02, 0.05, 0.15, 0.10, 0.23]
            else:
                probs = [0.10, 0.15, 0.15, 0.10, 0.05, 0.05, 0.10, 0.30]
                
            cat = np.random.choice(cats, p=probs)
            amt = np.random.exponential(40) + 5
            tx_date = start_date + timedelta(days=np.random.randint(0, date_range))
            
            transactions.append({
                'transaction_id': f"TX{tx_id_counter}",
                'customer_id': row['customer_id'],
                'timestamp': tx_date.strftime('%Y-%m-%d'),
                'amount': round(amt, 2),
                'ground_truth_category': cat
            })
            tx_id_counter += 1
            
    df_transactions = pd.DataFrame(transactions)
    
    df_transactions['predicted_category'] = df_transactions['ground_truth_category']
    noise_idx = df_transactions.sample(frac=0.08).index
    df_transactions.loc[noise_idx, 'predicted_category'] = np.random.choice(cats, len(noise_idx))

    drop_cols = ['trait_eco', 'trait_digital', 'trait_car_dep', 'trait_home_own', 
                 'prob_GP01', 'prob_GP02', 'prob_GP03', 'prob_GP04']
    df_customers = customers.drop(columns=drop_cols)
    df_customers['split'] = np.random.choice(['train', 'val', 'test'], num_customers, p=[0.7, 0.15, 0.15])
    
    return df_customers, df_transactions

# Execute generation
df_customers, df_transactions = generate_synthetic_data(5000, 40)

# Automatically create data folder if it doesn't exist
DATA_DIR.mkdir(parents=True, exist_ok=True)

df_customers.to_csv(DATA_DIR / "synthetic_customers.csv", index=False)
df_transactions.to_csv(DATA_DIR / "synthetic_transactions.csv", index=False)
print(f"Success: Generated synthetic_customers.csv and synthetic_transactions.csv in {DATA_DIR}")