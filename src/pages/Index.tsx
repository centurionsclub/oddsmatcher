import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { FilterSidebar } from "@/components/oddsmatcher/FilterSidebar";
import { MatchTable } from "@/components/oddsmatcher/MatchTable";
import { StatsCards } from "@/components/oddsmatcher/StatsCards";
import { Calculator, TrendingUp, Target, Shield } from "lucide-react";

const Index = () => {
  const [activeTab, setActiveTab] = useState("singola");

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b bg-card shadow-sm sticky top-0 z-10">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary/10 rounded-lg">
                <Calculator className="h-6 w-6 text-primary" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-foreground">OddsMatcher Pro</h1>
                <p className="text-sm text-muted-foreground">Sistema Professionale di Oddsmatching AAMS</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Aggiornato in tempo reale</span>
              <div className="h-2 w-2 bg-accent rounded-full animate-pulse" />
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Sidebar Filters */}
          <div className="lg:col-span-1">
            <FilterSidebar />
          </div>

          {/* Main Area */}
          <div className="lg:col-span-3 space-y-6">
            {/* Stats Cards */}
            <StatsCards />

            {/* Tabs Navigation */}
            <Card className="p-6">
              <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList className="grid w-full grid-cols-4 mb-6">
                  <TabsTrigger value="singola" className="flex items-center gap-2">
                    <Target className="h-4 w-4" />
                    Singola
                  </TabsTrigger>
                  <TabsTrigger value="multipla" className="flex items-center gap-2">
                    <Calculator className="h-4 w-4" />
                    Multipla
                  </TabsTrigger>
                  <TabsTrigger value="surebet" className="flex items-center gap-2">
                    <Shield className="h-4 w-4" />
                    Sure Bet
                  </TabsTrigger>
                  <TabsTrigger value="bestodds" className="flex items-center gap-2">
                    <TrendingUp className="h-4 w-4" />
                    Best Odds
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="singola">
                  <MatchTable type="singola" />
                </TabsContent>

                <TabsContent value="multipla">
                  <MatchTable type="multipla" />
                </TabsContent>

                <TabsContent value="surebet">
                  <MatchTable type="surebet" />
                </TabsContent>

                <TabsContent value="bestodds">
                  <MatchTable type="bestodds" />
                </TabsContent>
              </Tabs>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Index;
