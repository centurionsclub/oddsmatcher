import { Card } from "@/components/ui/card";
import { TrendingUp, Target, Shield, Zap } from "lucide-react";

export const StatsCards = () => {
  const stats = [
    {
      title: "Opportunità Attive",
      value: "127",
      change: "+12 oggi",
      icon: Target,
      color: "text-primary"
    },
    {
      title: "Profitto Medio",
      value: "€2.45",
      change: "+0.35 vs ieri",
      icon: TrendingUp,
      color: "text-accent"
    },
    {
      title: "Sure Bet",
      value: "8",
      change: "2 nuovi",
      icon: Shield,
      color: "text-warning"
    },
    {
      title: "Yield Medio",
      value: "96.2%",
      change: "+1.2%",
      icon: Zap,
      color: "text-accent"
    }
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {stats.map((stat, index) => {
        const Icon = stat.icon;
        return (
          <Card key={index} className="p-6 hover:shadow-lg transition-shadow">
            <div className="flex items-start justify-between">
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground font-medium">{stat.title}</p>
                <p className="text-3xl font-bold">{stat.value}</p>
                <p className="text-xs text-muted-foreground">{stat.change}</p>
              </div>
              <div className={`p-3 rounded-lg bg-primary/10 ${stat.color}`}>
                <Icon className="h-6 w-6" />
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
};
