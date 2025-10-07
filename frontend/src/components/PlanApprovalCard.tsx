'use client';

import React, { useState } from 'react';
import { CheckCircle2, XCircle, FileText, Layout, Search } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { cn } from '@/lib/utils';

export interface ApprovalData {
  plan: string;
  template?: string;
  findings?: string;
  routerId: string;
}

interface PlanApprovalCardProps {
  data: ApprovalData;
  onApprove: (routerId: string) => void;
  onRevise: (routerId: string, feedback: string) => void;
  className?: string;
}

export const PlanApprovalCard: React.FC<PlanApprovalCardProps> = ({
  data,
  onApprove,
  onRevise,
  className,
}) => {
  const [isReviseFeedbackOpen, setIsReviseFeedbackOpen] = useState(false);
  const [reviseFeedback, setReviseFeedback] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleApprove = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await onApprove(data.routerId);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReviseSubmit = async () => {
    if (isSubmitting || !reviseFeedback.trim()) return;
    setIsSubmitting(true);
    try {
      await onRevise(data.routerId, reviseFeedback.trim());
      setReviseFeedback('');
      setIsReviseFeedbackOpen(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReviseCancel = () => {
    setReviseFeedback('');
    setIsReviseFeedbackOpen(false);
  };

  return (
    <Card className={cn(
      // Use shading theme instead of borders
      "bg-muted/50 border-transparent shadow-lg",
      // Smooth entry animation
      "animate-in fade-in-0 slide-in-from-bottom-4 duration-500",
      // Dark mode compatibility with appropriate background
      "dark:bg-muted/30 dark:shadow-xl",
      className
    )}>
      <CardHeader className="pb-4">
        <CardTitle className="flex items-centre gap-2 text-lg">
          <FileText className="h-5 w-5 text-blue-600 dark:text-blue-400" />
          Plan Approval Required
        </CardTitle>
        <CardDescription>
          Review the generated plan and provide your approval or feedback for revisions.
        </CardDescription>
      </CardHeader>
      
      <CardContent className="space-y-4">
        {/* Tabs for Plan/Template/Findings with shaded active states */}
        <Tabs defaultValue="plan" className="w-full">
          <TabsList className="bg-muted/70 w-full">
            <TabsTrigger value="plan" className="flex-1">
              <Layout className="h-4 w-4 mr-1.5" />
              Plan
            </TabsTrigger>
            {data.template && (
              <TabsTrigger value="template" className="flex-1">
                <FileText className="h-4 w-4 mr-1.5" />
                Template
              </TabsTrigger>
            )}
            {data.findings && (
              <TabsTrigger value="findings" className="flex-1">
                <Search className="h-4 w-4 mr-1.5" />
                Findings
              </TabsTrigger>
            )}
          </TabsList>
          
          {/* Plan content with shaded container */}
          <TabsContent value="plan" className="mt-4">
            <div className="bg-muted/30 rounded-lg p-4 max-h-96 overflow-y-auto">
              <pre className="whitespace-pre-wrap text-sm text-foreground/90 font-mono">
                {data.plan}
              </pre>
            </div>
          </TabsContent>
          
          {/* Template content with shaded container */}
          {data.template && (
            <TabsContent value="template" className="mt-4">
              <div className="bg-muted/30 rounded-lg p-4 max-h-96 overflow-y-auto">
                <pre className="whitespace-pre-wrap text-sm text-foreground/90 font-mono">
                  {data.template}
                </pre>
              </div>
            </TabsContent>
          )}
          
          {/* Findings content with shaded container */}
          {data.findings && (
            <TabsContent value="findings" className="mt-4">
              <div className="bg-muted/30 rounded-lg p-4 max-h-96 overflow-y-auto">
                <pre className="whitespace-pre-wrap text-sm text-foreground/90 font-mono">
                  {data.findings}
                </pre>
              </div>
            </TabsContent>
          )}
        </Tabs>

        {/* Action buttons with conditional feedback area */}
        <div className="space-y-3 pt-2">
          {!isReviseFeedbackOpen ? (
            <div className="flex gap-3">
              {/* Approve button with green shading */}
              <Button
                onClick={handleApprove}
                disabled={isSubmitting}
                className={cn(
                  "flex-1 bg-green-600 hover:bg-green-700 text-white",
                  "dark:bg-green-600 dark:hover:bg-green-700",
                  "shadow-sm hover:shadow-md transition-all"
                )}
              >
                <CheckCircle2 className="h-4 w-4 mr-2" />
                {isSubmitting ? 'Approving...' : 'Approve Plan'}
              </Button>
              
              {/* Revise button with orange shading accents */}
              <Button
                onClick={() => setIsReviseFeedbackOpen(true)}
                disabled={isSubmitting}
                variant="outline"
                className={cn(
                  "flex-1 bg-orange-50 hover:bg-orange-100 border-orange-200",
                  "dark:bg-orange-950/20 dark:hover:bg-orange-950/40 dark:border-orange-800",
                  "text-orange-700 dark:text-orange-400 hover:text-orange-800 dark:hover:text-orange-300",
                  "shadow-sm hover:shadow-md transition-all"
                )}
              >
                <XCircle className="h-4 w-4 mr-2" />
                Request Revisions
              </Button>
            </div>
          ) : (
            // Feedback area with shaded container
            <div className="space-y-3 animate-in fade-in-0 slide-in-from-top-2 duration-300">
              <div className="bg-muted/40 rounded-lg p-4 border-l-4 border-l-orange-400 dark:border-l-orange-600">
                <label htmlFor="revision-feedback" className="block text-sm font-medium mb-2">
                  Revision Feedback
                </label>
                <Textarea
                  id="revision-feedback"
                  value={reviseFeedback}
                  onChange={(e) => setReviseFeedback(e.target.value)}
                  placeholder="Describe what changes you'd like to see in the plan..."
                  className="min-h-24 bg-background border-transparent shadow-sm"
                  disabled={isSubmitting}
                />
              </div>
              
              <div className="flex gap-2">
                <Button
                  onClick={handleReviseSubmit}
                  disabled={isSubmitting || !reviseFeedback.trim()}
                  className={cn(
                    "bg-orange-600 hover:bg-orange-700 text-white",
                    "dark:bg-orange-600 dark:hover:bg-orange-700",
                    "shadow-sm hover:shadow-md transition-all"
                  )}
                >
                  {isSubmitting ? 'Submitting...' : 'Submit Feedback'}
                </Button>
                <Button
                  onClick={handleReviseCancel}
                  variant="ghost"
                  disabled={isSubmitting}
                  className="hover:bg-muted/50"
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};