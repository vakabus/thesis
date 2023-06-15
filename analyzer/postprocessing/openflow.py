import sys

def load_rules(filename: str):
    with open(filename, 'r') as f:
        rules = []
        for line in f:
            rules.append([x.strip() for x in line.split(',')])
    table = {}
    for rule in rules:
        table[rule[0]] = rule[1:]
    return table

def rules_to_count(rules):
    res = {}
    for cookie, rule in rules.items():
        for x in rule:
            if x.startswith("n_packets="):
                res[cookie] = int(x[len("n_packets="):])
                break
        else:
            raise Exception("nebyl tam pocet", rule, cookie)
    return res
        

rules1 = load_rules(sys.argv[1])
rules2 = load_rules(sys.argv[2])

count1 = rules_to_count(rules1)
count2 = rules_to_count(rules2)

diff = {}
for cookie in count1:
    diff[cookie] = count2[cookie] - count1[cookie]

set(rules1.keys()).symmetric_difference(set(rules2.keys()))