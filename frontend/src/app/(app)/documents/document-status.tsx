import { FileImage, FileText, LoaderCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { fileKind, parseStatusLabel } from "@/lib/documents/model";
import { cn } from "@/lib/utils";

export function ParseStatusBadge({ status, className }: { status: string; className?: string }) {
  const label = parseStatusLabel(status);
  switch (status) {
    case "pending":
      return (
        <Badge variant="secondary" className={className}>
          <LoaderCircle className="animate-spin motion-reduce:animate-none" data-icon="inline-start" aria-hidden="true" />
          {label}
        </Badge>
      );
    case "extracted":
      return (
        <Badge variant="secondary" className={cn("bg-primary/10 text-primary dark:bg-primary/15", className)}>
          {label}
        </Badge>
      );
    case "needs_review":
      return (
        <Badge variant="warning" className={className}>
          {label}
        </Badge>
      );
    case "failed":
      return (
        <Badge variant="destructive" className={className}>
          {label}
        </Badge>
      );
    case "confirmed":
      return (
        <Badge variant="success" className={className}>
          {label}
        </Badge>
      );
    default:
      return (
        <Badge variant="secondary" className={className}>
          {label}
        </Badge>
      );
  }
}

export function DocumentFileIcon({ fileType, className }: { fileType: string; className?: string }) {
  const Icon = fileKind(fileType) === "pdf" ? FileText : FileImage;
  return <Icon className={cn("size-4 shrink-0 text-muted-foreground", className)} aria-hidden="true" />;
}
