"""The 20 fixed categories. Descriptions are by TYPE of business (no brand names) so the
same text works as LLM prompt material for any bank / city."""

CATEGORIES = {
    "Income": ("Salary, interest credited by the bank.", "Refunds, money from friends."),
    "Transfers": ("Money to or from a person, with or without a remark.", "Rent paid to a landlord (Rent)."),
    "Rent": ("House rent.", ""),
    "Food & Dining": ("Food delivery apps, restaurants, cafes.", "Grocery apps."),
    "Groceries": ("Supermarkets, quick-commerce grocery apps.", ""),
    "Transport": ("Cabs, bike taxis, fuel, metro.", "Flights (Travel)."),
    "Travel": ("Flights, trains, hotels.", "Daily commuting."),
    "Shopping": ("E-commerce, clothing, electronics.", "Groceries."),
    "Subscriptions": ("Streaming, music, cloud storage, software plans.",
                      "Phone bills (Utilities & Bills), gym (Health & Fitness)."),
    "Utilities & Bills": ("Electricity, phone, internet.", ""),
    "Health & Fitness": ("Pharmacies, clinics, gyms.", "Vets (Pets)."),
    "Personal Care": ("Salons, spas.", ""),
    "Entertainment": ("Movie and event tickets.", "Streaming (Subscriptions)."),
    "Books & Education": ("Bookshops, courses.", ""),
    "Pets": ("Vets, pet supplies.", ""),
    "Insurance": ("Health, life, vehicle premiums.", ""),
    "Investments": ("SIPs, mutual funds, stocks.", ""),
    "Cash Withdrawal": ("ATM withdrawals.", ""),
    "Fees & Charges": ("Bank charges, penalties.", ""),
    "Uncategorized": ("Anything the narration does not give enough information to classify.",
                      "Things that are merely hard to classify."),
}
CATEGORY_LIST = list(CATEGORIES)
assert len(CATEGORY_LIST) == 20

# Moving money is not spending it. Hidden from spend charts unless the user opts in.
MOVED_MONEY = {"Transfers", "Investments", "Cash Withdrawal"}
