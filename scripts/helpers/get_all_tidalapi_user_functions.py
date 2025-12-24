import inspect

import tidalapi.user

print("=== tidalapi.user.LoggedInUser methods ===\n")

# Get all public methods
for name in sorted(dir(tidalapi.user.LoggedInUser)):
    if name.startswith("_"):
        continue

    attr = getattr(tidalapi.user.LoggedInUser, name)

    if callable(attr):
        try:
            sig = str(inspect.signature(attr))
            # Clean up self parameter
            sig = sig.replace("(self)", "()")
            sig = sig.replace("(self, ", "(")
            print(f"• {name}{sig}")
        except:
            print(f"• {name}(...)")

        # Print docstring if available
        if hasattr(attr, "__doc__") and attr.__doc__:
            lines = attr.__doc__.strip().split("\n")
            for line in lines[:3]:  # First 3 lines
                if line.strip():
                    print(f"  {line.strip()}")
        print()
    elif isinstance(inspect.getattr_static(tidalapi.user.LoggedInUser, name), property):
        print(f"• {name} [property]")
        print()

print("\n=== Inherited from User ===\n")
print("• id")
print("• factory()")
print("• parse()")
