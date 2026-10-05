import copy


class EditHistory:
    def __init__(self, profile):
        self.current = copy.deepcopy(profile)
        self.past = []
        self.future = []

    def record(self, profile, merge=False):
        if profile == self.current:
            return False
        if not merge:
            self.past.append(self.current)
            self.past = self.past[-100:]
        self.current = copy.deepcopy(profile)
        self.future.clear()
        return True

    def undo(self):
        if not self.past:
            return None
        self.future.append(self.current)
        self.current = self.past.pop()
        return copy.deepcopy(self.current)

    def redo(self):
        if not self.future:
            return None
        self.past.append(self.current)
        self.current = self.future.pop()
        return copy.deepcopy(self.current)
