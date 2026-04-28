export type Participant = {
  artist_id: number;
  artist_name: string;
  role: "primary" | "collaborator" | "featured";
  status: "pending" | "accepted" | "rejected";
  approval_type: "split" | "feature" | "none";
  requires_approval: boolean;
  blocking: boolean;
  is_actionable_for_user: boolean;
  has_feature_context: boolean;
  rejection_reason: string | null;
  approved_at: string | null;
};

export type ParticipantVMGrouped = {
  actionableSplit: Participant[];
  actionableFeature: Participant[];
  pendingSplit: Participant[];
  pendingFeature: Participant[];
  accepted: Participant[];
  rejected: Participant[];
  other: Participant[];
};

export type ParticipantVMCounts = {
  actionable: number;
  actionableTotal: number;
  actionableSplit: number;
  actionableFeature: number;
  pendingSplit: number;
  pendingFeature: number;
};

export type ParticipantVM = {
  grouped: ParticipantVMGrouped;
  orderedParticipants: Participant[];
  counts: ParticipantVMCounts;
};

/**
 * Builds a UI-facing participant view model in one pass.
 * Keep this as the single source of frontend participant grouping logic.
 */
export function buildParticipantViewModel(participants: Participant[]): ParticipantVM {
  const grouped: ParticipantVMGrouped = {
    actionableSplit: [],
    actionableFeature: [],
    pendingSplit: [],
    pendingFeature: [],
    accepted: [],
    rejected: [],
    other: [],
  };

  for (const p of participants) {
    if (p.is_actionable_for_user) {
      if (p.blocking) {
        grouped.actionableSplit.push(p);
      } else {
        grouped.actionableFeature.push(p);
      }
    }

    if (p.status === "pending") {
      if (p.blocking) {
        grouped.pendingSplit.push(p);
      } else {
        grouped.pendingFeature.push(p);
      }
    } else if (p.status === "accepted") {
      grouped.accepted.push(p);
    } else if (p.status === "rejected") {
      grouped.rejected.push(p);
    } else {
      grouped.other.push(p);
    }
  }

  const orderedParticipants = [
    ...grouped.pendingSplit,
    ...grouped.pendingFeature,
    ...grouped.accepted,
    ...grouped.rejected,
    ...grouped.other,
  ];

  const actionableSplit = grouped.actionableSplit.length;
  const actionableFeature = grouped.actionableFeature.length;

  return {
    grouped,
    orderedParticipants,
    counts: {
      actionable: actionableSplit + actionableFeature,
      actionableTotal: actionableSplit + actionableFeature,
      actionableSplit,
      actionableFeature,
      pendingSplit: grouped.pendingSplit.length,
      pendingFeature: grouped.pendingFeature.length,
    },
  };
}
