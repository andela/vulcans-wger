class A:
    a = 3


class B(A):
    def pr(self):
        return self.a
Q = B()
print(B.a)
