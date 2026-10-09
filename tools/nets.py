import re, sys
text = open(sys.argv[1]).read()
for block in re.findall(r'\(net\s+\(code.*?(?=\(net\s+\(code|\Z)', text, re.S):
    name = re.search(r'\(name "([^"]*)"\)', block).group(1)
    pins = re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', block)
    print(f"{name:15} " + ", ".join(f"{r}.{p}" for r, p in pins))
