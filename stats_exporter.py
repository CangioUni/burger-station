class StatsExporter:
    def __init__(self, session_factory):
        pass
    def get_available_days(self): return []
    def generate_stats(self, day): return {}
    def export_to_excel(self, stats, path): pass
    def export_to_pdf(self, stats, path): pass
