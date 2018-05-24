# VictorOps Audits
Scripts for auditing a VictorOps account:

* VO_User_Audit.py - Uses the VO API to get a list of users and all their paging policy details, does an audits the list for bad policies (2 or fewer contact methods, default policy, only one page in the first 20 minutes etc.) then kicks out a .csv file with the results.

