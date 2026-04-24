import { apiGet } from "../client";

export interface EnumValue {
  value: string;
  label: string;
  color: string | null;
  description: string | null;
}

export interface EnumDescriptor {
  name: string;
  values: EnumValue[];
}

export const enumsApi = {
  get: (pid: string, name: string) =>
    apiGet<EnumDescriptor>(
      `/api/projects/${encodeURIComponent(pid)}/enums/${encodeURIComponent(name)}`,
    ),
};
