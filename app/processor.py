import pandas as pd
import numpy as np

MASTER_COLUMNS = [
    "% of ARV", "Auto offer", "Address", "City", "State", "Zip", "County", "Living Square Feet", "Year Built",
    "Lot (Acres)", "Lot (Square Feet)", "Land Use", "Property Type", "Property Use", "Subdivision", "APN",
    "Legal Description", "Units Count", "Bedrooms", "Bathrooms", "# of Stories", "Garage Type",
    "Garage Square Feet", "Carport", "Carport Area", "Air Conditioning Type", "Heating Type", "# of Fireplaces",
    "Owner 1 First Name", "Owner 1 Last Name", "Owner 2 First Name", "Owner 2 Last Name",
    "Owner 3 First Name", "Owner 3 Last Name", "Owner 4 First Name", "Owner 4 Last Name",
    "Owner Mailing Address", "Owner Mailing City", "Owner Mailing State", "Owner Mailing Zip",
    "Ownership Length (Months)", "Owner Type", "Owner Occupied", "Vacant?", "Listing Status", "Listing Price",
    "Days on Market", "Last Updated", "Listing Agent Full Name", "Listing Agent First Name",
    "Listing Agent Last Name", "Listing Agent Email", "Listing Agent Phone", "Listing Brokerage Name",
    "Listing Brokerage Phone", "Listing Brokerage Url", "MLS Type", "Last Sale Date", "Last Sale Amount",
    "Estimated Value", "Estimated Equity", "Estimated Equity Percent", "Open Mortgage Balance",
    "Recorded Mortgage Interest Rate", "Mortgage Document Date", "Mortgage Loan Type", "Lender Name",
    "Deed Type", "Position", "Tax Amount", "Assessment Year", "Assessed Total Value", "Assessed Land Value",
    "Assessed Improvement Value", "Assessed Improvement Percentage", "Market Value", "Market Land Value",
    "Market Improvement Value", "Market Improvement Percentage", "Status", "Default Amount", "Opening bid",
    "Recording Date", "Auction Date", "Auction Time", "Auction Courthouse", "Auction Address",
    "Auction City State", "Property #", "Owner-Time Factor", "Absentee Owner Factor", "Land Value Factor",
    "Improvement Factor", "Mortgage Factor", "Last Sale Price Factor", "ARV Factor", "Foreclosure Factor",
    "Vacant Factor", "Strain Factor", "CQ Factor", "Yr Built Factor", "Auto Offer Factor", "Factor SUM",
    "Propensity to Sell", "Median List Price"
]

def enforce_master_columns(df):
    df.columns = df.columns.str.strip()
    for i, col in enumerate(MASTER_COLUMNS):
        if col not in df.columns:
            df.insert(i, col, np.nan)
    df = df[MASTER_COLUMNS]
    return df

def calculate_columns(df):
    safe = lambda col: df[col] if col in df.columns else np.nan

    est_val = safe("Estimated Value")
    market_val = safe("Market Value")
    assessed_val = safe("Assessed Total Value")
    last_sale = safe("Last Sale Amount")
    living_sqft = safe("Living Square Feet")
    lot_sqft = safe("Lot (Square Feet)")
    assessed_land = safe("Assessed Land Value")
    market_land = safe("Market Land Value")
    assessed_imp = safe("Assessed Improvement Value")
    market_imp = safe("Market Improvement Value")
    eq_pct = safe("Estimated Equity Percent")
    owner_mailing = safe("Owner Mailing Address")
    address = safe("Address")
    last_sale_amt = safe("Last Sale Amount")
    vacant_col = safe("Vacant?")
    ai_pct = safe("Assessed Improvement Percentage")
    year_built = safe("Year Built")

    num_rows = len(df)

    block_names = [
        "Auto Offer",
        "Land Value Factor",
        "Improvement Factor",
        "ARV Factor"
    ]

    # 1. Calculate ARV candidates for formulas
    max_arv = pd.concat([est_val, market_val, assessed_val, last_sale], axis=1).max(axis=1)

    # 2. Auto offer logic (Block 1)
    auto_offer = []
    for i in range(num_rows):
        mval = max_arv.iloc[i]
        h = living_sqft.iloc[i] if not pd.isna(living_sqft.iloc[i]) else 0
        buv = assessed_land.iloc[i] if not pd.isna(assessed_land.iloc[i]) else 0
        byv = market_land.iloc[i] if not pd.isna(market_land.iloc[i]) else 0
        bxv = last_sale.iloc[i] if not pd.isna(last_sale.iloc[i]) else 0
        if pd.isna(mval):
            ao = np.nan
        elif mval >= 400000:
            ao = np.floor(mval*0.8 - h*65 - 20000)
            ao = ao - ao % 1000
        elif 300000 <= mval < 400000:
            ao = np.floor(mval*0.75 - h*50 - 20000)
            ao = ao - ao % 1000
        elif 250000 <= mval < 300000:
            ao = np.floor(mval*0.75 - h*40 - 20000)
            ao = ao - ao % 1000
        elif 200000 <= mval < 250000:
            ao = np.floor(mval*0.75 - h*35 - 20000)
            ao = ao - ao % 1000
        elif mval < 200000:
            ao = np.floor(mval*0.7 - h*30 - 20000)
            ao = max(ao - ao % 1000, 5000)
        else:
            ao = np.floor(max(buv, byv)*0.7 - 5000)
            ao = max(ao, 5000)
            ao = ao - ao % 1000
        auto_offer.append(ao)
    df["Auto offer"] = auto_offer
    yield "Step 1/19: Auto Offer calculations complete."

    # 3. % of ARV
    df["% of ARV"] = np.where(
        max_arv != 0,
        df["Auto offer"] / max_arv,
        np.nan
    )
    yield "Step 2/19: % of ARV calculation complete."

    # 4. Property #
    df["Property #"] = np.arange(1, len(df)+1)
    yield "Step 3/19: Property # calculation complete."

    # 5. Owner-Time Factor
    if "Ownership Length (Months)" in df:
        ao_col = pd.to_numeric(df["Ownership Length (Months)"], errors='coerce')
    else:
        ao_col = pd.Series(np.nan, index=df.index)
    df["Owner-Time Factor"] = np.where(
        ao_col.isnull(), 0.5,
        np.where(ao_col >= 240, 1,
        np.where((ao_col >= 60) & (ao_col < 240), 0.75, 0.5))
    )
    yield "Step 4/19: Owner-Time Factor calculation complete."

    # 6. Absentee Owner Factor
    df["Absentee Owner Factor"] = np.where(owner_mailing == address, 0.25, 1)
    yield "Step 5/19: Absentee Owner Factor calculation complete."

    # 7. Land Value Factor (Block 2)
    lvf = []
    for i in range(num_rows):
        bh = est_val.iloc[i]
        buv = assessed_land.iloc[i]
        byv = market_land.iloc[i]
        k = lot_sqft.iloc[i]
        try:
            val1 = max(buv, byv)/bh if bh else np.nan
        except Exception:
            val1 = np.nan
        try:
            val2 = k/max(bh, buv, byv) if not pd.isna(bh) else np.nan
        except Exception:
            val2 = np.nan
        if pd.isnull(val1):
            res1 = np.nan
        elif val1 < 0.25:
            res1 = 0
        elif 0.25 < val1 <= 0.75:
            res1 = 0.5
        elif 0.75 < val1 <= 0.9:
            res1 = 0.75
        else:
            res1 = 1
        if pd.isnull(val2):
            res2 = np.nan
        elif val2 <= (1/40):
            res2 = 0
        elif (1/40) < val2 <= (1/20):
            res2 = 0.5
        elif (1/20) < val2 <= (1/10):
            res2 = 0.75
        else:
            res2 = 1
        lvf.append(max(res1, res2))
    df["Land Value Factor"] = lvf
    yield "Step 6/19: Land Value Factor calculation complete."

    # 8. Improvement Factor (Block 3)
    improvement_factor = []
    for i in range(num_rows):
        try:
            cond1 = max(assessed_imp.iloc[i], market_imp.iloc[i]) > 100000
        except Exception:
            cond1 = False
        try:
            cond2 = last_sale_amt.iloc[i] / est_val.iloc[i] > 0.75
        except Exception:
            cond2 = False
        improvement_factor.append(0.25 if (cond1 or cond2) else 1)
    df["Improvement Factor"] = improvement_factor
    yield "Step 7/19: Improvement Factor calculation complete."

    # 9. Mortgage Factor
    bj = eq_pct
    df["Mortgage Factor"] = np.where(bj == 100, 1,
                             np.where((bj < 100) & (bj >= 70), 0.875,
                             np.where((bj < 70) & (bj > 50), 0.75, 0.5)))
    yield "Step 8/19: Mortgage Factor calculation complete."

    # 10. Last Sale Price Factor
    bg = last_sale_amt
    bh = est_val
    ratio = bg / bh
    df["Last Sale Price Factor"] = np.where(ratio >= 0.5, 0.5,
                                   np.where((ratio <= 0.5) & (ratio >= 0.25), 0.75, 1))
    yield "Step 9/19: Last Sale Price Factor calculation complete."

    # 11. ARV Factor (Block 4)
    arv_candidates = pd.concat([est_val, assessed_val, last_sale], axis=1)
    max_arv2 = arv_candidates.max(axis=1)
    median_bh = est_val.median()
    arvf = []
    for i in range(num_rows):
        val = max_arv2.iloc[i]
        if val < median_bh*0.5:
            res = 1
        elif median_bh*0.5 <= val < median_bh*0.75:
            res = 0.75
        elif median_bh*0.75 <= val < median_bh:
            res = 0.5
        elif val > median_bh:
            res = 0.25
        else:
            res = 0
        arvf.append(res)
    df["ARV Factor"] = arvf
    yield "Step 10/19: ARV Factor calculation complete."

    # 12. Foreclosure Factor (uses "Recording Date" for year, blank=0, <2023=0, >=2023=1)
    def get_recording_year(val):
        if pd.isna(val) or str(val).strip() == "":
            return 0
        try:
            year = pd.to_datetime(val, errors='coerce').year
            if pd.isna(year):
                return 0
            return 0 if year < 2023 else 1
        except Exception:
            return 0
    df["Foreclosure Factor"] = df["Recording Date"].apply(get_recording_year)
    yield "Step 11/19: Foreclosure Factor calculation complete."

    # 13. Vacant Factor
    df["Vacant Factor"] = df["Vacant?"].apply(lambda x: 1 if str(x).strip() == "1" else 0)
    yield "Step 12/19: Vacant Factor calculation complete."

    # 14. Strain Factor (uses Last Sale Price Factor as CQ)
    def strain_factor_row(row):
        cq = pd.to_numeric(row.get("Last Sale Price Factor", 0), errors='coerce')
        bj = pd.to_numeric(row.get("Estimated Equity Percent", 0), errors='coerce')
        if cq >= 0.75 and bj < 50:
            return 1
        elif cq >= 0.75 and 50 <= bj < 75:
            return 0.75
        elif cq >= 0.75 and 75 <= bj < 100:
            return 0.5
        else:
            return 0
    df["Strain Factor"] = df.apply(strain_factor_row, axis=1)
    yield "Step 13/19: Strain Factor calculation complete."

    # 15. CQ Factor (uses "Air Conditioning Type")
    df["CQ Factor"] = df["Air Conditioning Type"].apply(
        lambda z: 0 if isinstance(z, str) and str(z).strip().upper() in ["CENTRAL", "EVAPORATIVE", "REFRIGERATOR", "YES"]
        else (np.nan if pd.isna(z) or str(z).strip() == "" else 1)
    )
    yield "Step 14/19: CQ Factor calculation complete."

    # 16. Yr Built Factor
    i = year_built
    yr_built_factor = []
    for val in i:
        if pd.isna(val):
            res = np.nan
        elif val >= 2020:
            res = 0
        elif 2010 <= val < 2020:
            res = 0.1
        elif 2000 <= val < 2010:
            res = 0.25
        elif 1978 <= val < 2000:
            res = 0.5
        elif 1950 <= val < 1978:
            res = 0.75
        elif val <= 1950:
            res = 1
        else:
            res = 1
        yr_built_factor.append(res)
    df["Yr Built Factor"] = yr_built_factor
    yield "Step 15/19: Yr Built Factor calculation complete."

    # 17. Auto Offer Factor
    b = df["Auto offer"].replace('[\$,]', '', regex=True).replace('', np.nan)
    auto_offer_factor = []
    for v in b:
        try:
            v = float(v)
        except:
            v = np.nan
        if pd.isna(v):
            res = np.nan
        elif v < 50000:
            res = 1
        elif 50000 <= v < 100000:
            res = 0.875
        elif 100000 <= v < 150000:
            res = 0.75
        elif 150000 <= v < 200000:
            res = 0.625
        elif 200000 <= v < 300000:
            res = 0.5
        elif v >= 300000:
            res = 0.25
        else:
            res = 0
        auto_offer_factor.append(res)
    df["Auto Offer Factor"] = auto_offer_factor
    yield "Step 16/19: Auto Offer Factor calculation complete."

    # 18. Factor SUM - robust conversion to numeric before summing!
    factor_cols = [
        "Owner-Time Factor", "Absentee Owner Factor", "Land Value Factor", "Improvement Factor",
        "Mortgage Factor", "Last Sale Price Factor", "ARV Factor", "Foreclosure Factor", "Vacant Factor",
        "Strain Factor", "CQ Factor", "Yr Built Factor", "Auto Offer Factor"
    ]
    for col in factor_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df["Factor SUM"] = df[factor_cols].sum(axis=1, min_count=1)
    yield "Step 17/19: Factor SUM calculation complete."

    # 19. Propensity to Sell
    cy = df["Factor SUM"]
    df["Propensity to Sell"] = np.where(cy >= 10, "High",
                                np.where((cy < 10) & (cy >= 9), "Mid-High",
                                np.where((cy < 9) & (cy >= 7), "Med", "Low")))
    yield "Step 18/19: Propensity to Sell calculation complete."

    # 20. Median List Price: median of Estimated Value
    median_list_price = est_val.median()
    df["Median List Price"] = median_list_price
    yield "Step 19/19: Median List Price calculation complete."

    # ---- FORMATTING for visible output ----
    yield "Formatting final columns..."
    df["% of ARV"] = df["% of ARV"].apply(lambda x: "" if pd.isna(x) else f"{int(round(x * 100))}%")
    df["Auto offer"] = df["Auto offer"].apply(lambda x: "" if pd.isna(x) else f"${int(x):,}")

    yield df
