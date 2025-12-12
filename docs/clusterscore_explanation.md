# ClusterScore Explained (Like You're 12)

Imagine you are trying to guess if the cool kids at school are planning a secret party. You can't hear them talking, but you can see them buying party supplies.

The **Playbook** is your list of rules to spot the party:

1.  **Multiple Kids:** It's not a party if just one kid buys cups. You need a group (Cluster Buys).
2.  **Popular Kids:** If the Class President (CEO) and Treasurer (CFO) are buying supplies, it's a bigger deal than if the random kid from gym class (Director) is doing it (Role Weight).
3.  **Spending Cash:** They need to be spending real money, not just pennies (Value).
4.  **Going All In:** It means way more if a kid spends their *entire allowance* on supplies versus just their pocket change (Relative Value).
5.  **No Teachers:** We don't care if the teachers (Funds) are buying coffee; we only care about the students (Insiders).
6.  **Speedy Delivery:** If they buy supplies and tell everyone immediately, they are excited. If they wait weeks to mention it, maybe it's not that important (Days to File).
7.  **Buyers, Not Sellers:** We like kids who usually buy, not kids who are always selling. If they have been selling their lunch every day and suddenly buy one apple, we are suspicious (Sale/Purchase Ratio).

The **ClusterScore** is a single number—like a grade from 0 to 100—that tells you how likely it is that the party is happening.

**Here is how we calculate the grade (the ClusterScore):**

We start at **0** and add (or subtract) points:

*   **+ Points for Popular Kids (Role Score):**
    *   **CFO (Treasurer):** +3 points. They know the budget. If they spend, it's real.
    *   **CEO (President):** +2 points. They run the show.
    *   **Directors (Random Kids):** +1 point. Good to see, but less important.
    *   *So, if a CFO and CEO both buy, that's +5 points right there.*

*   **+ Points for Going All In (Avg % Change):**
    *   **This is the superpower.**
    *   If a kid doubles the amount of supplies they own (+100%), that's huge.
    *   If a kid already owns 1,000 cups and buys 10 more (+1%), that's boring.
    *   **We give big points (weight: 5.0) if the group is increasing their stash by a large percentage.**

*   **+ Points for the Crowd (People Count):**
    *   We add +1 point for every single person who buys.
    *   *5 people buying is better than 2.*

*   **+ Points for Money (Value):**
    *   We add points based on how much cash they spent. But we use a math trick (logarithms) so that one rich kid spending a billion dollars doesn't break the scale.
    *   *Spending $10 million is better than $10,000, but not 1,000 times better.*

*   **- Penalty for Outsiders (Fund Ratio):**
    *   We **subtract** points if too many "teachers" (Investment Funds) are involved.
    *   If half the buyers are hedge funds, the score drops. That's just business, not a secret party.

*   **- Penalty for Waiting (Days to File):**
    *   We **subtract** points if they took a long time to tell the SEC (filing date - trade date).
    *   Filing the next day is great (low penalty). Waiting 2 weeks is suspicious (high penalty).

*   **- Penalty for Sellers (Sale/Purchase Ratio):**
    *   We **subtract** points if these insiders are frequent sellers.
    *   We look at their past trades. If they sold 10x more than they bought, we subtract points (weight: -3.0). We want insiders who are "pure buyers" or hold their shares.

**How it fits the Playbook:**

The Playbook says "Look for A, B, C, D, and E."
The **ClusterScore** does the math for you:

*   **Low Score (e.g., 15):** Two Directors bought a tiny amount, they filed the form 2 weeks late, and they usually sell stock. Boring.
*   **High Score (e.g., 85):** The CFO, CEO, and VP all bought $500k each, **doubling their positions**, they filed the form the next day, and they rarely sell. **This is the signal.**

Instead of reading 100 lines of data, you just sort by **ClusterScore** and look at the top of the list. That's the party.
